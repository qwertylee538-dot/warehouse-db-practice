"""
Second cleanup pass: while the bug in step18 was active, more than one
duplicate 'legitimate-looking' RETURN movement got created for order
#1 / SKU-005. This deletes EVERY RETURN movement linked to order #1
and re-creates exactly one correct one.
"""

from step1_connect import get_connection


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        DELETE FROM stock_movements
        WHERE movement_type = 'RETURN' AND note LIKE 'Return against order #1:%'
        RETURNING id;
        """
    )
    deleted = cursor.fetchall()
    print(f"Deleted {len(deleted)} RETURN movement(s) linked to order #1.")

    cursor.execute("SELECT id FROM products WHERE sku = 'SKU-005';")
    product_id = cursor.fetchone()[0]
    cursor.execute("SELECT store_id FROM orders WHERE id = 1;")
    store_id = cursor.fetchone()[0]

    cursor.execute(
        """
        INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note, reason)
        VALUES (%s, %s, 'RETURN', 1, %s, %s);
        """,
        (product_id, store_id, "Return against order #1: Не подошла модель, клиент передумал", "Не подошла модель, клиент передумал"),
    )
    connection.commit()
    print("Re-created exactly one correct return (quantity=1).")

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()