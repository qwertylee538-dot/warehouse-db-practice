"""
One-off correction: step9's bulk test data generator had a bias bug
(explained in chat) that made SKU-006 receive only OUT movements,
pushing its stock deeply negative. This script adds a single
correcting IN movement to bring every product's stock back to
non-negative, so later steps aren't blocked by this artifact of the
test data.
"""

from step1_connect import get_connection


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT product_id, store_id,
               SUM(CASE WHEN movement_type = 'IN' THEN quantity ELSE -quantity END) AS stock
        FROM stock_movements
        GROUP BY product_id, store_id
        HAVING SUM(CASE WHEN movement_type = 'IN' THEN quantity ELSE -quantity END) < 0;
        """
    )
    negative_rows = cursor.fetchall()

    if not negative_rows:
        print("Nothing negative found — no correction needed.")
    else:
        for product_id, store_id, stock in negative_rows:
            correction = abs(stock) + 10
            cursor.execute(
                """
                INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note)
                VALUES (%s, %s, 'IN', %s, %s);
                """,
                (product_id, store_id, correction, "Correction for step9 bulk-data bias bug"),
            )
            print(f"  product_id={product_id} store_id={store_id}: was {stock}, corrected by +{correction}")
        connection.commit()
        print("Done — all negative balances corrected.")

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()