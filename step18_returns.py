"""
STEP 18: Customer returns.

WHY RETURN IS ITS OWN movement_type, NOT JUST ANOTHER 'IN':
A return physically puts stock back on the shelf, exactly like an IN
movement — but it means something completely different for the
business. A manager tracking "how much are we buying from suppliers"
should NOT see returns mixed into that number. So, same idea as
WRITE_OFF in step17: we widen the CHECK constraint again to also
allow 'RETURN', and require a reason.

THE IMPORTANT BUSINESS RULE: YOU CAN ONLY RETURN WHAT WAS ACTUALLY SOLD.
return_stock() checks the original order: the product must have been
part of a FULFILLED order, and the total quantity ever returned
against that order item can't exceed what was originally bought.

BUG FOUND AND FIXED WHILE BUILDING THIS:
already_returned_quantity() originally checked the `reason` column for
the "Return against order #N" marker text — but that text is actually
written into `note`, not `reason` (`reason` only holds the short,
customer-given reason). Checking the wrong column meant the function
always returned 0, so a duplicate return was never blocked. Fixed by
checking `note` instead.
"""

from step1_connect import get_connection


def constraint_exists(cursor, constraint_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = %s;",
        (constraint_name,),
    )
    return cursor.fetchone() is not None


def ensure_return_support(cursor) -> None:
    if constraint_exists(cursor, "stock_movements_movement_type_check"):
        cursor.execute(
            "ALTER TABLE stock_movements DROP CONSTRAINT stock_movements_movement_type_check;"
        )
    cursor.execute(
        """
        ALTER TABLE stock_movements
        ADD CONSTRAINT stock_movements_movement_type_check
        CHECK (movement_type IN ('IN', 'OUT', 'WRITE_OFF', 'RETURN'));
        """
    )
    print("  movement_type can now also be 'RETURN'.")


def already_returned_quantity(cursor, order_id: int, product_id: int) -> float:
    cursor.execute(
        """
        SELECT COALESCE(SUM(quantity), 0)
        FROM stock_movements
        WHERE movement_type = 'RETURN' AND note LIKE %s AND product_id = %s;
        """,
        (f"Return against order #{order_id}:%", product_id),
    )
    return cursor.fetchone()[0]


def return_stock(connection, order_id: int, sku: str, quantity: float, reason: str) -> bool:
    cursor = connection.cursor()

    cursor.execute("SELECT id FROM products WHERE sku = %s FOR UPDATE;", (sku,))
    row = cursor.fetchone()
    if row is None:
        print(f"  REJECTED: unknown SKU '{sku}'.")
        connection.rollback()
        cursor.close()
        return False
    product_id = row[0]

    cursor.execute("SELECT status, store_id FROM orders WHERE id = %s;", (order_id,))
    order_row = cursor.fetchone()
    if order_row is None:
        print(f"  REJECTED: no order with id={order_id}.")
        connection.rollback()
        cursor.close()
        return False
    status, store_id = order_row
    if status != "fulfilled":
        print(f"  REJECTED: order #{order_id} is '{status}', not 'fulfilled' — nothing to return.")
        connection.rollback()
        cursor.close()
        return False

    cursor.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM order_items WHERE order_id = %s AND product_id = %s;",
        (order_id, product_id),
    )
    originally_bought = cursor.fetchone()[0]
    already_returned = already_returned_quantity(cursor, order_id, product_id)
    remaining_returnable = originally_bought - already_returned

    if quantity > remaining_returnable:
        print(
            f"  REJECTED: order #{order_id} only has {remaining_returnable} of "
            f"'{sku}' left that can be returned (bought {originally_bought}, "
            f"already returned {already_returned})."
        )
        connection.rollback()
        cursor.close()
        return False

    cursor.execute(
        """
        INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note, reason)
        VALUES (%s, %s, 'RETURN', %s, %s, %s);
        """,
        (product_id, store_id, quantity, f"Return against order #{order_id}: {reason}", reason),
    )
    connection.commit()
    print(f"  OK: returned {quantity} of '{sku}' from order #{order_id} — reason: '{reason}'.")
    cursor.close()
    return True


def returns_report(cursor) -> None:
    print("\n=== Returns by product and reason ===")
    cursor.execute(
        """
        SELECT p.sku, p.name, m.reason, SUM(m.quantity) AS total_returned
        FROM stock_movements m
        JOIN products p ON p.id = m.product_id
        WHERE m.movement_type = 'RETURN'
        GROUP BY p.sku, p.name, m.reason
        ORDER BY total_returned DESC;
        """
    )
    rows = cursor.fetchall()
    headers = ["SKU", "Product", "Reason", "Total returned"]
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

    print("Ensuring return support exists (widened CHECK constraint)...")
    ensure_return_support(cursor)
    connection.commit()
    cursor.close()

    print("\nTrying to return 1 more Bosch drill from order #1 (should be REJECTED now — already fully returned)...")
    return_stock(connection, order_id=1, sku="SKU-005", quantity=1, reason="test")

    cursor = connection.cursor()
    returns_report(cursor)
    cursor.close()

    connection.close()


if __name__ == "__main__":
    main()