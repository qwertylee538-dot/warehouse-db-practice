"""
STEP 10: Prices and inventory value — turning unit counts into money.

WHAT'S NEW:
So far every report answered "how many units." A real warehouse
manager usually cares just as much about "how many RUBLES is sitting
on the shelf." This script:
  1. Adds a `price` column to products (ALTER TABLE, same safe,
     re-runnable pattern as step7's schema changes).
  2. Sets a sample price for each existing product.
  3. Adds a report: inventory value per store (units * price, summed).

WHY price LIVES ON products, NOT ON EACH MOVEMENT:
We're keeping this simple: one "current" price per product, not a
price history. A more advanced real system would record the price
AT THE TIME of each movement too (because prices change over time,
and a 2024 shipment's value shouldn't change every time this year's
price changes) — but that's a bigger step (an extra price_history
table), so we leave it as a known simplification here and just note
it, rather than partially building it.
"""

from step1_connect import get_connection

PRICES = {
    "SKU-001": 350.00,    # cement, per bag
    "SKU-002": 12.00,     # brick, per piece
    "SKU-003": 2.50,      # screws, per piece
    "SKU-004": 3.00,      # dowels, per piece
    "SKU-005": 8500.00,   # Bosch drill, per piece
    "SKU-006": 45.00,     # cable, per meter
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


def ensure_price_column(cursor) -> None:
    if not column_exists(cursor, "products", "price"):
        print("  Adding price column to products...")
        cursor.execute("ALTER TABLE products ADD COLUMN price NUMERIC(10, 2);")
    else:
        print("  price column already exists — skipping.")


def set_sample_prices(cursor) -> None:
    for sku, price in PRICES.items():
        cursor.execute(
            "UPDATE products SET price = %s WHERE sku = %s;",
            (price, sku),
        )
        print(f"  {sku} -> {price} RUB")


def inventory_value_by_store(cursor) -> None:
    print("\n=== Inventory value per store ===")
    cursor.execute(
        """
        SELECT
            s.name AS store,
            COALESCE(SUM(
                (CASE WHEN m.movement_type = 'IN' THEN m.quantity ELSE -m.quantity END)
                * p.price
            ), 0) AS inventory_value_rub
        FROM stores s
        LEFT JOIN stock_movements m ON m.store_id = s.id
        LEFT JOIN products p ON p.id = m.product_id
        GROUP BY s.name
        ORDER BY s.name;
        """
    )
    rows = cursor.fetchall()
    headers = ["Store", "Inventory value (RUB)"]
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, value in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(value)))
    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print("-" * len(header_line))
    for row in rows:
        print("  ".join(str(value).ljust(col_widths[i]) for i, value in enumerate(row)))


def most_valuable_products(cursor, top_n: int = 3) -> None:
    print(f"\n=== Top {top_n} most valuable products (all stores combined) ===")
    cursor.execute(
        """
        SELECT
            p.sku,
            p.name,
            p.price,
            COALESCE(SUM(CASE WHEN m.movement_type = 'IN' THEN m.quantity ELSE -m.quantity END), 0) AS current_stock,
            p.price * COALESCE(SUM(CASE WHEN m.movement_type = 'IN' THEN m.quantity ELSE -m.quantity END), 0) AS total_value
        FROM products p
        LEFT JOIN stock_movements m ON m.product_id = p.id
        GROUP BY p.sku, p.name, p.price
        ORDER BY total_value DESC
        LIMIT %s;
        """,
        (top_n,),
    )
    rows = cursor.fetchall()
    headers = ["SKU", "Name", "Price", "Current stock", "Total value"]
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

    print("Ensuring products has a price column...")
    ensure_price_column(cursor)
    connection.commit()

    print("\nSetting sample prices...")
    set_sample_prices(cursor)
    connection.commit()

    inventory_value_by_store(cursor)
    most_valuable_products(cursor, top_n=3)

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()