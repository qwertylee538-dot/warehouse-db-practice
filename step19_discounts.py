"""
STEP 19: Discounts and promotions — a price reduction that's only
active for a specific date range.

WHY THIS IS SEPARATE FROM price_history (step13):
price_history tracks the PERMANENT price of a product over time.
A discount is different: it's a TEMPORARY reduction, tied to specific
dates, that should automatically stop applying once it ends. Modeling
it as its own table with start/end dates means the discount just
naturally stops mattering once today's date passes end_date — no
extra code needed to "turn it off."

HOW effective_price() WORKS:
  1. Start with the product's current price (from price_history, step13).
  2. Look for any discount on this product where TODAY falls between
     start_date and end_date.
  3. If found, apply it (either a percentage off, or a fixed amount off).
  4. If several discounts somehow overlap, we deliberately pick the
     single BEST one for the customer.
"""

from datetime import date, timedelta

from step1_connect import get_connection
from step13_price_history import get_current_price


def ensure_discounts_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS discounts (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id),
            discount_type VARCHAR(10) NOT NULL CHECK (discount_type IN ('percent', 'amount')),
            discount_value NUMERIC(10, 2) NOT NULL CHECK (discount_value > 0),
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            CHECK (end_date >= start_date)
        );
        """
    )


def create_discount(cursor, sku: str, discount_type: str, discount_value: float, start_date: date, end_date: date) -> None:
    cursor.execute("SELECT id FROM products WHERE sku = %s;", (sku,))
    product_id = cursor.fetchone()[0]
    cursor.execute(
        """
        INSERT INTO discounts (product_id, discount_type, discount_value, start_date, end_date)
        VALUES (%s, %s, %s, %s, %s);
        """,
        (product_id, discount_type, discount_value, start_date, end_date),
    )
    print(f"  {sku}: {discount_value}{'%' if discount_type == 'percent' else ' RUB'} off, {start_date} to {end_date}")


def effective_price(cursor, product_id: int, on_date=None):
    if on_date is None:
        on_date = date.today()

    base_price = get_current_price(cursor, product_id)
    if base_price is None:
        return None, None

    cursor.execute(
        """
        SELECT discount_type, discount_value
        FROM discounts
        WHERE product_id = %s AND start_date <= %s AND end_date >= %s;
        """,
        (product_id, on_date, on_date),
    )
    active_discounts = cursor.fetchall()
    if not active_discounts:
        return base_price, None

    best_price = base_price
    best_discount_value = None
    for discount_type, discount_value in active_discounts:
        if discount_type == "percent":
            candidate_price = base_price * (1 - discount_value / 100)
        else:
            candidate_price = base_price - discount_value
        candidate_price = max(candidate_price, 0)
        if candidate_price < best_price:
            best_price = candidate_price
            best_discount_value = discount_value

    return round(best_price, 2), best_discount_value


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    print("Ensuring discounts table exists...")
    ensure_discounts_table(cursor)
    connection.commit()

    today = date.today()

    print("\nCreating an active discount (Bosch drills, 10% off, active right now)...")
    create_discount(
        cursor,
        sku="SKU-005",
        discount_type="percent",
        discount_value=10,
        start_date=today - timedelta(days=1),
        end_date=today + timedelta(days=7),
    )

    print("\nCreating an EXPIRED discount (cement, was 50 RUB off, ended last week)...")
    create_discount(
        cursor,
        sku="SKU-001",
        discount_type="amount",
        discount_value=50,
        start_date=today - timedelta(days=30),
        end_date=today - timedelta(days=7),
    )
    connection.commit()

    cursor.execute("SELECT id FROM products WHERE sku = 'SKU-005';")
    drill_id = cursor.fetchone()[0]
    price, discount = effective_price(cursor, drill_id)
    print(f"\nSKU-005 (Bosch drill) effective price today: {price} RUB (discount applied: {discount})")

    cursor.execute("SELECT id FROM products WHERE sku = 'SKU-001';")
    cement_id = cursor.fetchone()[0]
    price, discount = effective_price(cursor, cement_id)
    print(f"SKU-001 (cement) effective price today: {price} RUB (discount applied: {discount} — should be None, discount expired)")

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()