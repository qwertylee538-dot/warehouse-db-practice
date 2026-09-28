"""
STEP 21: Regulatory tracking — modeling systems like EGAIS (alcohol)
and Mercury/Vetis (animal products), where the state assigns a UNIQUE
mark to every single physical unit of certain goods, and that mark can
be "spent" (used) exactly once, ever.

WHAT REAL EGAIS / MERKURIY ACTUALLY DO (simplified but accurate idea):
Regulated goods (alcohol, meat, dairy) in Russia require every unit —
every bottle, every batch — to carry a unique government-issued code.
When that unit is received, the code gets registered as "in stock."
When it's sold or moved, the SAME code must be declared as "used" —
and critically, the same code can NEVER be marked used twice.

HOW THIS IS MODELED HERE:
  - products.requires_tracking (BOOLEAN) — marks which products are
    regulated.
  - tracking_marks: one row per unique government mark.
  - receive_with_marks(): registers N new marks as 'in_stock' AND
    creates the matching IN movement, in one transaction.
  - ship_with_marks(): takes SPECIFIC mark codes and flips them to
    'used', creating the matching OUT movement. Reusing an
    already-'used' mark is REJECTED.
"""

from step1_connect import get_connection


def column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s;
        """,
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def ensure_tracking_support(cursor) -> None:
    if not column_exists(cursor, "products", "requires_tracking"):
        print("  Adding requires_tracking column to products...")
        cursor.execute(
            "ALTER TABLE products ADD COLUMN requires_tracking BOOLEAN NOT NULL DEFAULT FALSE;"
        )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tracking_marks (
            id SERIAL PRIMARY KEY,
            code VARCHAR(50) NOT NULL UNIQUE,
            product_id INTEGER NOT NULL REFERENCES products(id),
            store_id INTEGER NOT NULL REFERENCES stores(id),
            status VARCHAR(10) NOT NULL DEFAULT 'in_stock'
                CHECK (status IN ('in_stock', 'used'))
        );
        """
    )
    cursor.execute(
        "UPDATE products SET requires_tracking = TRUE WHERE sku = 'SKU-005';"
    )


def receive_with_marks(connection, sku: str, store_id: int, marks: list) -> bool:
    cursor = connection.cursor()
    cursor.execute("SELECT id, requires_tracking FROM products WHERE sku = %s FOR UPDATE;", (sku,))
    row = cursor.fetchone()
    if row is None:
        print(f"  REJECTED: unknown SKU '{sku}'.")
        connection.rollback()
        cursor.close()
        return False
    product_id, requires_tracking = row
    if not requires_tracking:
        print(f"  REJECTED: {sku} is not a regulated product — use ordinary receiving instead.")
        connection.rollback()
        cursor.close()
        return False

    for code in marks:
        cursor.execute(
            "INSERT INTO tracking_marks (code, product_id, store_id) VALUES (%s, %s, %s) ON CONFLICT (code) DO NOTHING RETURNING id;",
            (code, product_id, store_id),
        )
        if cursor.fetchone() is None:
            print(f"  REJECTED: mark '{code}' already exists (would be a duplicate government code).")
            connection.rollback()
            cursor.close()
            return False

    cursor.execute(
        """
        INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note)
        VALUES (%s, %s, 'IN', %s, %s);
        """,
        (product_id, store_id, len(marks), f"Received {len(marks)} tracked unit(s) with government marks"),
    )
    connection.commit()
    print(f"  OK: received {len(marks)} tracked unit(s) of {sku}, marks registered as in_stock.")
    cursor.close()
    return True


def ship_with_marks(connection, sku: str, store_id: int, marks: list) -> bool:
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM products WHERE sku = %s FOR UPDATE;", (sku,))
    row = cursor.fetchone()
    if row is None:
        print(f"  REJECTED: unknown SKU '{sku}'.")
        connection.rollback()
        cursor.close()
        return False
    product_id = row[0]

    for code in marks:
        cursor.execute(
            "SELECT status FROM tracking_marks WHERE code = %s AND product_id = %s FOR UPDATE;",
            (code, product_id),
        )
        mark_row = cursor.fetchone()
        if mark_row is None:
            print(f"  REJECTED: mark '{code}' does not exist for {sku}.")
            connection.rollback()
            cursor.close()
            return False
        if mark_row[0] != "in_stock":
            print(f"  REJECTED: mark '{code}' is already '{mark_row[0]}' — cannot sell the same unit twice.")
            connection.rollback()
            cursor.close()
            return False

    for code in marks:
        cursor.execute(
            "UPDATE tracking_marks SET status = 'used' WHERE code = %s;",
            (code,),
        )

    cursor.execute(
        """
        INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note)
        VALUES (%s, %s, 'OUT', %s, %s);
        """,
        (product_id, store_id, len(marks), f"Sold {len(marks)} tracked unit(s), marks: {', '.join(marks)}"),
    )
    connection.commit()
    print(f"  OK: sold {len(marks)} tracked unit(s) of {sku}, marks flipped to used.")
    cursor.close()
    return True


def tracking_report(cursor) -> None:
    print("\n=== Tracking marks status ===")
    cursor.execute(
        """
        SELECT p.sku, tm.status, COUNT(*)
        FROM tracking_marks tm
        JOIN products p ON p.id = tm.product_id
        GROUP BY p.sku, tm.status
        ORDER BY p.sku, tm.status;
        """
    )
    for sku, status, count in cursor.fetchall():
        print(f"  {sku}: {count} mark(s) {status}")


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    print("Ensuring regulatory tracking support exists...")
    ensure_tracking_support(cursor)
    connection.commit()
    cursor.close()

    print("\nReceiving 3 tracked drills with unique government marks...")
    receive_with_marks(
        connection,
        sku="SKU-005",
        store_id=1,
        marks=["EGAIS-000001", "EGAIS-000002", "EGAIS-000003"],
    )

    print("\nSelling 2 of them by their specific marks...")
    ship_with_marks(connection, sku="SKU-005", store_id=1, marks=["EGAIS-000001", "EGAIS-000002"])

    print("\nTrying to sell EGAIS-000001 AGAIN (should be rejected — already used)...")
    ship_with_marks(connection, sku="SKU-005", store_id=1, marks=["EGAIS-000001"])

    cursor = connection.cursor()
    tracking_report(cursor)
    cursor.close()

    connection.close()


if __name__ == "__main__":
    main()