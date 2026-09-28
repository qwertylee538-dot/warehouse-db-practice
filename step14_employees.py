"""
STEP 14: Employees — tracking WHO performed each stock movement.

WHY THIS MATTERS IN A REAL WAREHOUSE:
If something goes wrong — a wrong quantity shipped, stock that doesn't
match reality — the first question a manager asks is "who touched
this?" Without an employee_id on every movement, that question is
unanswerable from the data alone. Real systems like 1C always tie
every document/action to the logged-in user who created it.

WHAT'S NEW: MAKING A COLUMN OPTIONAL ON PURPOSE.
Every movement from step3-step13 was inserted WITHOUT an employee — we
never had this column, so it must be allowed to be NULL going forward
(we're not going to fabricate fake authors for old, already-committed
history). This is a realistic and common migration situation: you add
tracking going forward, and old rows honestly show "unknown" instead
of a fake guess.
"""

from step1_connect import get_connection

EMPLOYEES = [
    ("Иванова Анна", "кладовщик"),
    ("Петров Сергей", "кладовщик"),
    ("Сидорова Мария", "менеджер склада"),
]


def column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s;
        """,
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def ensure_employees_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(150) NOT NULL UNIQUE,
            position VARCHAR(100) NOT NULL,
            hired_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )


def ensure_employee_id_column(cursor) -> None:
    if not column_exists(cursor, "stock_movements", "employee_id"):
        print("  Adding employee_id column to stock_movements (nullable — old rows stay 'unknown')...")
        cursor.execute(
            "ALTER TABLE stock_movements ADD COLUMN employee_id INTEGER REFERENCES employees(id);"
        )
    else:
        print("  employee_id column already exists — skipping.")


def insert_employees(cursor) -> dict:
    name_to_id = {}
    for full_name, position in EMPLOYEES:
        cursor.execute(
            "INSERT INTO employees (full_name, position) VALUES (%s, %s) ON CONFLICT (full_name) DO NOTHING;",
            (full_name, position),
        )
        cursor.execute("SELECT id FROM employees WHERE full_name = %s;", (full_name,))
        name_to_id[full_name] = cursor.fetchone()[0]
    return name_to_id


def ship_stock_as_employee(connection, product_id: int, store_id: int, quantity: float, note: str, employee_id: int) -> bool:
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM products WHERE id = %s FOR UPDATE;", (product_id,))
    if cursor.fetchone() is None:
        print(f"  REJECTED: no product with id={product_id}.")
        connection.rollback()
        cursor.close()
        return False

    cursor.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN movement_type = 'IN' THEN quantity ELSE -quantity END), 0)
        FROM stock_movements WHERE product_id = %s AND store_id = %s;
        """,
        (product_id, store_id),
    )
    stock = cursor.fetchone()[0]
    if quantity > stock:
        print(f"  REJECTED: only {stock} available.")
        connection.rollback()
        cursor.close()
        return False

    cursor.execute(
        """
        INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note, employee_id)
        VALUES (%s, %s, 'OUT', %s, %s, %s);
        """,
        (product_id, store_id, quantity, note, employee_id),
    )
    connection.commit()
    print(f"  OK: shipped {quantity}, recorded under employee_id={employee_id}.")
    cursor.close()
    return True


def employee_activity_report(cursor) -> None:
    print("\n=== Employee activity ===")
    cursor.execute(
        """
        SELECT
            COALESCE(e.full_name, 'Unknown (before employee tracking)') AS employee,
            COUNT(m.id) AS movements_handled,
            COALESCE(SUM(m.quantity), 0) AS total_quantity
        FROM stock_movements m
        LEFT JOIN employees e ON e.id = m.employee_id
        GROUP BY e.full_name
        ORDER BY movements_handled DESC;
        """
    )
    rows = cursor.fetchall()
    headers = ["Employee", "Movements handled", "Total quantity"]
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, value in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(value)))
    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print("-" * len(header_line))
    for row in rows:
        print("  ".join(str(value).ljust(col_widths[i]) for i, value in enumerate(row)))


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    print("Ensuring employees table exists...")
    ensure_employees_table(cursor)
    connection.commit()

    print("Ensuring stock_movements has an employee_id column...")
    ensure_employee_id_column(cursor)
    connection.commit()

    print("Inserting sample employees...")
    employee_ids = insert_employees(cursor)
    connection.commit()
    anna_id = employee_ids["Иванова Анна"]

    print("\nShipping stock as a specific employee...")
    ship_stock_as_employee(
        connection,
        product_id=6,
        store_id=1,
        quantity=5,
        note="Order pickup, counter by Anna",
        employee_id=anna_id,
    )

    cursor = connection.cursor()
    employee_activity_report(cursor)
    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()