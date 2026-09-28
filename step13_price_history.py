"""
STEP 13: Price history — prices change over time, and past value
shouldn't change retroactively.

THE BUG step10 HAD, IN HINDSIGHT:
step10 gave each product ONE current price. That's fine for "what is
this worth right now," but it silently breaks historical accuracy: if
cement cost 350 RUB when you received 100 bags last month, and today
the price is 400 RUB, step10's report would say that OLD shipment is
now worth 100 * 400 — as if the past changed too. Real accounting
never works that way: a shipment's value is fixed at the price that
was true THE DAY it happened.

THE FIX: A price_history TABLE INSTEAD OF ONE COLUMN.
Instead of products.price being overwritten every time the price
changes, we keep every price that was EVER set, each with the date it
became effective:

    price_history (product_id, price, effective_from)

"The current price" becomes a QUERY, not a stored fact: "the most
recent price_history row for this product whose effective_from is not
in the future." And "the price at some past date" is the same query
with a different date.
"""

from step1_connect import get_connection


def ensure_price_history_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id),
            price NUMERIC(10, 2) NOT NULL,
            effective_from TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )


def migrate_existing_prices(cursor) -> None:
    cursor.execute(
        """
        INSERT INTO price_history (product_id, price, effective_from)
        SELECT p.id, p.price, NOW()
        FROM products p
        WHERE p.price IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM price_history ph WHERE ph.product_id = p.id
          );
        """
    )
    print(f"  Migrated {cursor.rowcount} existing price(s) into price_history.")


def set_new_price(cursor, sku: str, new_price: float) -> None:
    cursor.execute("SELECT id FROM products WHERE sku = %s;", (sku,))
    product_id = cursor.fetchone()[0]
    cursor.execute(
        "INSERT INTO price_history (product_id, price) VALUES (%s, %s);",
        (product_id, new_price),
    )
    print(f"  {sku}: new price {new_price} RUB recorded (old price still in history).")


def get_current_price(cursor, product_id: int):
    cursor.execute(
        """
        SELECT price FROM price_history
        WHERE product_id = %s AND effective_from <= NOW()
        ORDER BY effective_from DESC
        LIMIT 1;
        """,
        (product_id,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def show_price_history(cursor, sku: str) -> None:
    print(f"\n=== Price history for {sku} ===")
    cursor.execute(
        """
        SELECT ph.price, ph.effective_from
        FROM price_history ph
        JOIN products p ON p.id = ph.product_id
        WHERE p.sku = %s
        ORDER BY ph.effective_from;
        """,
        (sku,),
    )
    for price, effective_from in cursor.fetchall():
        print(f"  {effective_from} -> {price} RUB")


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    print("Ensuring price_history table exists...")
    ensure_price_history_table(cursor)
    connection.commit()

    print("Migrating existing product prices into price_history...")
    migrate_existing_prices(cursor)
    connection.commit()

    print("\nRecording a price change for SKU-001 (cement got more expensive)...")
    set_new_price(cursor, "SKU-001", 400.00)
    connection.commit()

    show_price_history(cursor, "SKU-001")

    cursor.execute("SELECT id FROM products WHERE sku = %s;", ("SKU-001",))
    product_id = cursor.fetchone()[0]
    current = get_current_price(cursor, product_id)
    print(f"\nCurrent price of SKU-001 right now: {current} RUB")
    print("(Both prices are preserved — old shipments keep their original value,")
    print(" only NEW calculations from now on use the new price.)")

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()