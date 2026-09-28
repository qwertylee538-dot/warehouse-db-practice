"""
STEP 15: Barcodes and scan-to-find — modeling what your handheld
terminal actually does.

WHAT'S NEW:
Your real job scans a barcode with a handheld terminal, and the
terminal looks up which product that code belongs to — nobody types
SKUs by hand at the shelf. This step adds a `barcode` column to
products (a UNIQUE constraint, since two different products can never
legally share one barcode) and a find_by_barcode() function that
mimics exactly that lookup.

WHY UNIQUE MATTERS HERE SPECIFICALLY:
If barcode weren't UNIQUE, a data-entry mistake could accidentally
give two different products the same code — then scanning that code
would be ambiguous, which is exactly the kind of bug a real warehouse
system must make IMPOSSIBLE, not just unlikely. The database enforces
this, so it can never happen even by accident.
"""

from step1_connect import get_connection

BARCODES = {
    "SKU-001": "4601234500011",
    "SKU-002": "4601234500028",
    "SKU-003": "4601234500035",
    "SKU-004": "4601234500042",
    "SKU-005": "4601234500059",
    "SKU-006": "4601234500066",
}


def column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s;
        """,
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def ensure_barcode_column(cursor) -> None:
    if not column_exists(cursor, "products", "barcode"):
        print("  Adding barcode column to products (UNIQUE)...")
        cursor.execute("ALTER TABLE products ADD COLUMN barcode VARCHAR(20) UNIQUE;")
    else:
        print("  barcode column already exists — skipping.")


def set_barcodes(cursor) -> None:
    for sku, barcode in BARCODES.items():
        cursor.execute(
            "UPDATE products SET barcode = %s WHERE sku = %s;",
            (barcode, sku),
        )
        print(f"  {sku} -> {barcode}")


def find_by_barcode(cursor, barcode: str, store_id: int) -> None:
    cursor.execute(
        "SELECT id, sku, name FROM products WHERE barcode = %s;",
        (barcode,),
    )
    row = cursor.fetchone()
    if row is None:
        print(f"  Scan '{barcode}': NOT FOUND — no product has this barcode.")
        return

    product_id, sku, name = row
    cursor.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN movement_type = 'IN' THEN quantity ELSE -quantity END), 0)
        FROM stock_movements WHERE product_id = %s AND store_id = %s;
        """,
        (product_id, store_id),
    )
    stock = cursor.fetchone()[0]
    print(f"  Scan '{barcode}': FOUND -> {sku} '{name}', current stock at store {store_id}: {stock}")


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    print("Ensuring products has a barcode column...")
    ensure_barcode_column(cursor)
    connection.commit()

    print("\nSetting sample barcodes...")
    set_barcodes(cursor)
    connection.commit()

    print("\nSimulating scans at the handheld terminal (store 1)...")
    find_by_barcode(cursor, "4601234500059", store_id=1)
    find_by_barcode(cursor, "0000000000000", store_id=1)

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()