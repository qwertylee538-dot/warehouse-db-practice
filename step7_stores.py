"""
STEP 7: Multiple stores, each with its own independent stock.

THE DESIGN CHOICE: ONE DATABASE, A store_id COLUMN — NOT SEPARATE DATABASES.
A tempting first idea is "give each shop its own separate database."
Real systems almost never do this, because then a simple question like
"how many drills do we have across the whole company?" would require
connecting to every store's database separately and adding the results
together by hand — fragile and slow. Instead, we add ONE column,
store_id, to stock_movements. Now:
  - stock for store #1 alone  = filter WHERE store_id = 1
  - stock for store #2 alone  = filter WHERE store_id = 2
  - stock for the whole chain = no filter at all, same query
This gives each store its own independent, correct stock number while
keeping the ability to see the whole picture in one query. This is the
same idea used by real inventory systems (including the 1C system you
use at work) — a "branch" or "store" identifier attached to each
transaction, not a separate database per branch.

WHY THIS SCRIPT USES ALTER TABLE INSTEAD OF DROP TABLE:
Earlier steps (step2) safely used DROP TABLE IF EXISTS because there
was no real data worth keeping yet. Now we have data from steps 3-6
that's worth preserving as we evolve the schema, so this script
instead uses ALTER TABLE to add to what's already there — this is a
tiny taste of what a real "migration" looks like. Every change below
is written to be safe to run more than once (using IF NOT EXISTS /
ON CONFLICT checks), in case you run this script twice by accident.
"""

from step1_connect import get_connection

STORES = [
    ("Магазин №1 — Центральный", "ул. Ленина, 10"),
    ("Магазин №2 — Северный", "ул. Северная, 45"),
]

STORE_2_MOVEMENTS = [
    # (sku, movement_type, quantity, note)
    ("SKU-001", "IN", 300, "Store 2 opening stock — cement"),
    ("SKU-001", "OUT", 50, "Store 2 — local order"),
    ("SKU-005", "IN", 4, "Store 2 opening stock — Bosch drills"),
    ("SKU-006", "IN", 200, "Store 2 opening stock — cable"),
]


def ensure_stores_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS stores (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            address VARCHAR(300)
        );
        """
    )


def column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s;
        """,
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def ensure_store_id_column(cursor, default_store_id: int) -> None:
    if not column_exists(cursor, "stock_movements", "store_id"):
        print("  Adding store_id column to stock_movements...")
        cursor.execute(
            "ALTER TABLE stock_movements ADD COLUMN store_id INTEGER REFERENCES stores(id);"
        )
        print(f"  Backfilling existing movements to store id={default_store_id}...")
        cursor.execute(
            "UPDATE stock_movements SET store_id = %s WHERE store_id IS NULL;",
            (default_store_id,),
        )
        cursor.execute(
            "ALTER TABLE stock_movements ALTER COLUMN store_id SET NOT NULL;"
        )
    else:
        print("  store_id column already exists — skipping.")


def insert_stores(cursor) -> dict:
    name_to_id = {}
    for name, address in STORES:
        cursor.execute(
            """
            INSERT INTO stores (name, address)
            VALUES (%s, %s)
            ON CONFLICT (name) DO NOTHING;
            """,
            (name, address),
        )
        cursor.execute("SELECT id FROM stores WHERE name = %s;", (name,))
        store_id = cursor.fetchone()[0]
        name_to_id[name] = store_id
        print(f"  Store '{name}' -> id={store_id}")
    return name_to_id


def insert_store_2_movements(cursor, store_2_id: int) -> None:
    for sku, movement_type, quantity, note in STORE_2_MOVEMENTS:
        cursor.execute("SELECT id FROM products WHERE sku = %s;", (sku,))
        row = cursor.fetchone()
        if row is None:
            print(f"  Skipping {sku} — product not found.")
            continue
        product_id = row[0]
        cursor.execute(
            """
            INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (product_id, store_2_id, movement_type, quantity, note),
        )
        print(f"  Store 2: {movement_type} {quantity} of {sku} — {note}")


def stock_by_store_report(cursor) -> None:
    print("\n=== Current stock per product, per store ===")
    cursor.execute(
        """
        SELECT
            s.name AS store,
            p.sku,
            p.name AS product,
            COALESCE(SUM(CASE WHEN m.movement_type = 'IN' THEN m.quantity ELSE -m.quantity END), 0) AS current_stock
        FROM stores s
        CROSS JOIN products p
        LEFT JOIN stock_movements m ON m.product_id = p.id AND m.store_id = s.id
        GROUP BY s.name, p.sku, p.name
        HAVING COALESCE(SUM(CASE WHEN m.movement_type = 'IN' THEN m.quantity ELSE -m.quantity END), 0) != 0
        ORDER BY s.name, p.sku;
        """
    )
    rows = cursor.fetchall()
    headers = ["Store", "SKU", "Product", "Current stock"]
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

    print("Ensuring stores table exists...")
    ensure_stores_table(cursor)
    connection.commit()

    print("Inserting stores...")
    store_ids = insert_stores(cursor)
    connection.commit()

    store_1_id = store_ids["Магазин №1 — Центральный"]
    store_2_id = store_ids["Магазин №2 — Северный"]

    print("\nEnsuring stock_movements has a store_id column...")
    ensure_store_id_column(cursor, default_store_id=store_1_id)
    connection.commit()

    print("\nInserting sample movements for store 2...")
    insert_store_2_movements(cursor, store_2_id)
    connection.commit()

    stock_by_store_report(cursor)

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()