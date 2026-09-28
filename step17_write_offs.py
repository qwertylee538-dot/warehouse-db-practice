"""
STEP 17: Write-offs (списание брака/порчи) — a distinct movement type
for goods that leave the shelf WITHOUT being sold.

WHY THIS NEEDS ITS OWN movement_type, NOT JUST ANOTHER 'OUT':
Up to now, every 'OUT' movement has implicitly meant "sold / shipped to
a customer." But damaged, expired, or broken goods leaving the shelf
are a completely different business event — nobody paid for them, and
a manager reviewing the books needs to be able to tell these apart
from real sales at a glance (for insurance, loss analysis, and knowing
which products keep getting damaged). So this step changes the
CHECK constraint on stock_movements.movement_type from just
('IN', 'OUT') to ('IN', 'OUT', 'WRITE_OFF'), and adds a mandatory
`reason` for every write-off.

CHANGING A CHECK CONSTRAINT THAT ALREADY EXISTS:
You can't just add a new allowed value to an existing CHECK constraint
directly — PostgreSQL requires DROPping the old constraint and ADDing
a new one with the updated rule.

BUG FOUND WHILE BUILDING THIS (and fixed below):
The original step2 schema declared movement_type as VARCHAR(3) — just
enough characters for "IN" or "OUT". 'WRITE_OFF' is 9 characters, so
inserting it failed with "StringDataRightTruncation" until the COLUMN
itself was widened, not just the CHECK constraint. This is a realistic
lesson: a CHECK constraint controls which VALUES are allowed, but the
column's declared TYPE/length is a separate limit that has to be
widened on its own.
"""

from step1_connect import get_connection


def constraint_exists(cursor, constraint_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = %s;",
        (constraint_name,),
    )
    return cursor.fetchone() is not None


def ensure_write_off_support(cursor) -> None:
    """Widen the movement_type column and its CHECK constraint to also
    allow 'WRITE_OFF', and add a `reason` column (required only for
    write-offs — NULL is fine for ordinary IN/OUT movements).
    """
    # Widen the column itself FIRST — VARCHAR(3) physically cannot
    # hold the 9-character string 'WRITE_OFF', regardless of what the
    # CHECK constraint allows.
    print("  Widening movement_type column from VARCHAR(3) to VARCHAR(20)...")
    cursor.execute("ALTER TABLE stock_movements ALTER COLUMN movement_type TYPE VARCHAR(20);")

    # PostgreSQL auto-names a CHECK constraint like
    # "stock_movements_movement_type_check" unless you named it
    # yourself in step2 — that's the default name we look for here.
    if constraint_exists(cursor, "stock_movements_movement_type_check"):
        print("  Dropping the old movement_type CHECK constraint (IN/OUT only)...")
        cursor.execute(
            "ALTER TABLE stock_movements DROP CONSTRAINT stock_movements_movement_type_check;"
        )
    cursor.execute(
        """
        ALTER TABLE stock_movements
        ADD CONSTRAINT stock_movements_movement_type_check
        CHECK (movement_type IN ('IN', 'OUT', 'WRITE_OFF'));
        """
    )
    print("  New constraint in place: movement_type can now also be 'WRITE_OFF'.")

    cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = 'stock_movements' AND column_name = 'reason';"
    )
    if cursor.fetchone() is None:
        print("  Adding reason column to stock_movements...")
        cursor.execute("ALTER TABLE stock_movements ADD COLUMN reason VARCHAR(200);")


def write_off_stock(connection, product_id: int, store_id: int, quantity: float, reason: str, employee_id=None) -> bool:
    """Remove damaged/spoiled/broken stock — same safety checks as
    ship_stock (can't write off more than physically exists), but
    tagged as 'WRITE_OFF' with a mandatory reason instead of 'OUT'.
    """
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
        print(f"  REJECTED: only {stock} available, cannot write off {quantity}.")
        connection.rollback()
        cursor.close()
        return False

    cursor.execute(
        """
        INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note, reason, employee_id)
        VALUES (%s, %s, 'WRITE_OFF', %s, %s, %s, %s);
        """,
        (product_id, store_id, quantity, f"Write-off: {reason}", reason, employee_id),
    )
    connection.commit()
    print(f"  OK: wrote off {quantity} — reason: '{reason}'.")
    cursor.close()
    return True


def write_off_report(cursor) -> None:
    """Total written-off quantity per product, per reason — this is
    what lets a manager spot a pattern (e.g. "this product keeps
    arriving damaged from this supplier").
    """
    print("\n=== Write-offs by product and reason ===")
    cursor.execute(
        """
        SELECT p.sku, p.name, m.reason, SUM(m.quantity) AS total_written_off
        FROM stock_movements m
        JOIN products p ON p.id = m.product_id
        WHERE m.movement_type = 'WRITE_OFF'
        GROUP BY p.sku, p.name, m.reason
        ORDER BY total_written_off DESC;
        """
    )
    rows = cursor.fetchall()
    headers = ["SKU", "Product", "Reason", "Total written off"]
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

    print("Ensuring write-off support exists (widened column + CHECK constraint + reason column)...")
    ensure_write_off_support(cursor)
    connection.commit()
    cursor.close()

    print("\nWriting off some damaged brick (SKU-002 is product_id=2)...")
    write_off_stock(connection, product_id=2, store_id=1, quantity=15, reason="Повреждена при разгрузке")

    print("\nTrying to write off an absurd amount (should be rejected)...")
    write_off_stock(connection, product_id=2, store_id=1, quantity=999999, reason="test")

    cursor = connection.cursor()
    write_off_report(cursor)
    cursor.close()

    connection.close()


if __name__ == "__main__":
    main()