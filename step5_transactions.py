"""
STEP 5: Transactions — making multi-step operations safe.

THE PROBLEM TRANSACTIONS SOLVE:
Imagine "processing a shipment" really means two things happening
together: (1) record an OUT movement, and (2) check that we didn't
just ship more than we have in stock. If step 1 succeeds but the
script crashes before step 2 finishes checking, the database is left
in a "half-done" state — a movement is recorded that maybe shouldn't
have been allowed. That's very hard to notice and even harder to fix
later, because nothing *looks* broken — the data is just quietly wrong.

WHAT A TRANSACTION ACTUALLY IS:
A transaction groups several SQL statements into one "all or nothing"
unit. While it's open, none of the changes are visible to anyone else
and nothing is permanent yet. At the end you choose:
  - COMMIT   -> make every change in the transaction permanent, all at once
  - ROLLBACK -> undo every change in the transaction, as if none of it
                had ever happened
There is no in-between state — either everything happened, or nothing did.

psycopg2 AND TRANSACTIONS:
psycopg2 actually starts a transaction automatically the moment you
call cursor.execute() for the first time on a connection — that's why
every earlier script in this series needed an explicit
connection.commit() at the end to save anything at all! What's new in
this file is that we now deliberately use connection.rollback() too,
inside a try/except, to cancel a transaction when a business-rule
check fails.

THE FUNCTION BELOW: ship_stock()
"Ship stock" for a product should never be allowed to make its stock
go negative in this simple system (you cannot ship out what physically
isn't on the shelf). So before we commit the OUT movement, we check
the resulting stock. If it would go negative, we roll back — the
INSERT we just ran is completely undone, as if we'd never called
execute() at all.
"""

from step1_connect import get_connection


def get_current_stock(cursor, product_id: int) -> float:
    """Calculate current stock for one product the same way step4 did —
    SUM of IN minus SUM of OUT from the movement history.
    """
    cursor.execute(
        """
        SELECT COALESCE(
            SUM(CASE WHEN movement_type = 'IN' THEN quantity ELSE -quantity END),
            0
        )
        FROM stock_movements
        WHERE product_id = %s;
        """,
        (product_id,),
    )
    return cursor.fetchone()[0]


def ship_stock(connection, product_id: int, quantity: float, note: str) -> bool:
    """Try to record an OUT movement for a shipment. Returns True if it
    succeeded, False if it was rejected (not enough stock) — in the
    False case, the database ends up completely unchanged, as if this
    function had never been called.
    """
    cursor = connection.cursor()

    # Step 1: look up the product name for a friendlier message. If the
    # product_id doesn't exist at all, this returns None.
    cursor.execute("SELECT name FROM products WHERE id = %s;", (product_id,))
    row = cursor.fetchone()
    if row is None:
        print(f"  REJECTED: no product with id={product_id}.")
        cursor.close()
        return False
    product_name = row[0]

    # Step 2: insert the OUT movement. Nothing is permanent yet — this
    # is only visible inside this same transaction so far.
    cursor.execute(
        """
        INSERT INTO stock_movements (product_id, movement_type, quantity, note)
        VALUES (%s, 'OUT', %s, %s);
        """,
        (product_id, quantity, note),
    )

    # Step 3: recalculate stock *as if* the insert above had already
    # been committed — SQL inside the same transaction always sees its
    # own uncommitted changes, so this SUM already includes the OUT
    # movement we just inserted.
    new_stock = get_current_stock(cursor, product_id)

    if new_stock < 0:
        # The shipment would leave stock negative — that's not allowed.
        # ROLLBACK undoes the INSERT above completely; it's as if we
        # never ran it.
        connection.rollback()
        print(
            f"  REJECTED: shipping {quantity} of '{product_name}' would leave "
            f"stock at {new_stock} (negative). Change rolled back — nothing saved."
        )
        cursor.close()
        return False

    # Everything checks out — make the INSERT permanent.
    connection.commit()
    print(f"  OK: shipped {quantity} of '{product_name}'. New stock: {new_stock}.")
    cursor.close()
    return True


def main() -> None:
    connection = get_connection()

    print("Attempt 1: a normal, valid shipment of SKU-001 (product id=1)")
    ship_stock(connection, product_id=1, quantity=10, note="Test shipment - should succeed")

    print("\nAttempt 2: a huge shipment that would push SKU-001 negative")
    ship_stock(connection, product_id=1, quantity=999999, note="Test shipment - should be rejected")

    print("\nAttempt 3: a shipment for a product id that doesn't exist")
    ship_stock(connection, product_id=9999, quantity=1, note="Test shipment - should be rejected")

    connection.close()


if __name__ == "__main__":
    main()