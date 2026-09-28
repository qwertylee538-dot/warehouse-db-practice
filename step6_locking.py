"""
STEP 6: Row locking — preventing race conditions with SELECT ... FOR UPDATE.

THE BUG THIS FILE DEMONSTRATES (a "race condition"):
Imagine two warehouse operators both ship the same product at almost
the same moment. Each one:
  1. reads the current stock
  2. checks "is my shipment quantity <= current stock?"
  3. if yes, inserts the OUT movement and commits
If both operators do step 1 at the same instant, they can BOTH see the
same (still-correct-looking) stock number, BOTH pass the check in step
2, and BOTH commit in step 3 — even though, combined, they shipped more
than was ever on the shelf. Neither operation looks wrong on its own;
the bug only exists in the gap between "read" and "write", and it only
shows up under real concurrent load, which is exactly why these bugs
are so easy to miss in casual testing.

WHY THIS FILE USES threading:
To make this timing gap happen reliably (instead of "maybe, if you're
unlucky"), we run two Python threads at once, each with its OWN
database connection (psycopg2 connections are not safe to share
between threads), and we insert a deliberate time.sleep() in the
middle of the critical section to force both threads to be "in the
gap" between reading stock and committing at the same time. This is a
test harness to make an intermittent real-world bug happen every time,
not something you'd normally do in production code.

THE FIX: SELECT ... FOR UPDATE
Adding "FOR UPDATE" to a SELECT tells PostgreSQL: "lock the row(s) this
query touches until my transaction ends (COMMIT or ROLLBACK)." If a
second transaction tries to SELECT ... FOR UPDATE the SAME row, it
doesn't error — it simply WAITS in line until the first transaction
finishes. Only then does it run its own SELECT, and by then it sees
the up-to-date stock number (including whatever the first transaction
just committed). This closes the timing gap completely: there is no
longer any moment where two transactions can both act on stale data.
"""

import threading
import time

from step1_connect import get_connection


def get_current_stock(cursor, product_id: int) -> float:
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


def unsafe_ship(product_id: int, quantity: float, worker_name: str) -> None:
    """The BUGGY version — reads stock, waits (simulating real-world
    processing time), THEN checks and writes. No locking at all, so two
    threads can both read the same stale stock value.
    """
    connection = get_connection()
    cursor = connection.cursor()

    stock = get_current_stock(cursor, product_id)
    print(f"  [{worker_name}] sees stock = {stock}, wants to ship {quantity}")

    time.sleep(1)

    if quantity > stock:
        print(f"  [{worker_name}] REJECTED — not enough stock (saw {stock}).")
        connection.rollback()
    else:
        cursor.execute(
            """
            INSERT INTO stock_movements (product_id, movement_type, quantity, note)
            VALUES (%s, 'OUT', %s, %s);
            """,
            (product_id, quantity, f"unsafe_ship by {worker_name}"),
        )
        connection.commit()
        print(f"  [{worker_name}] shipped {quantity} (thought stock was {stock}).")

    cursor.close()
    connection.close()


def safe_ship(product_id: int, quantity: float, worker_name: str) -> None:
    """The FIXED version — locks the product row FIRST with
    SELECT ... FOR UPDATE, so a second thread trying to ship the same
    product has to wait its turn instead of reading stale data.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT id FROM products WHERE id = %s FOR UPDATE;", (product_id,))

    stock = get_current_stock(cursor, product_id)
    print(f"  [{worker_name}] (locked) sees stock = {stock}, wants to ship {quantity}")

    time.sleep(1)

    if quantity > stock:
        print(f"  [{worker_name}] REJECTED — not enough stock (saw {stock}).")
        connection.rollback()
    else:
        cursor.execute(
            """
            INSERT INTO stock_movements (product_id, movement_type, quantity, note)
            VALUES (%s, 'OUT', %s, %s);
            """,
            (product_id, quantity, f"safe_ship by {worker_name}"),
        )
        connection.commit()
        print(f"  [{worker_name}] shipped {quantity} (stock was {stock}).")

    cursor.close()
    connection.close()


def run_demo(ship_function, product_id: int, quantity_each: float) -> None:
    t1 = threading.Thread(target=ship_function, args=(product_id, quantity_each, "Operator-A"))
    t2 = threading.Thread(target=ship_function, args=(product_id, quantity_each, "Operator-B"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()
    stock = get_current_stock(cursor, product_id=5)
    cursor.close()
    connection.close()

    quantity_each = (stock // 2) + 1
    print(f"Starting stock of product id=5: {stock}")
    print(f"Each operator will try to ship {quantity_each} (individually OK, together too much)\n")

    print("=== UNSAFE version (no locking) — watch for the bug ===")
    run_demo(unsafe_ship, product_id=5, quantity_each=quantity_each)

    connection = get_connection()
    cursor = connection.cursor()
    stock_after_unsafe = get_current_stock(cursor, product_id=5)
    cursor.close()
    connection.close()
    print(f"Stock after UNSAFE demo: {stock_after_unsafe} (negative means the bug happened!)\n")

    if stock_after_unsafe < 0:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO stock_movements (product_id, movement_type, quantity, note)
            VALUES (%s, 'IN', %s, %s);
            """,
            (5, abs(stock_after_unsafe) + 5, "Correction after unsafe_ship demo"),
        )
        connection.commit()
        cursor.close()
        connection.close()
        print("  (restocked a bit so the SAFE demo below has a clean starting point)\n")

    connection = get_connection()
    cursor = connection.cursor()
    stock = get_current_stock(cursor, product_id=5)
    cursor.close()
    connection.close()
    quantity_each = (stock // 2) + 1
    print(f"Starting stock of product id=5: {stock}")
    print(f"Each operator will try to ship {quantity_each} again\n")

    print("=== SAFE version (SELECT ... FOR UPDATE) — bug should be gone ===")
    run_demo(safe_ship, product_id=5, quantity_each=quantity_each)

    connection = get_connection()
    cursor = connection.cursor()
    stock_after_safe = get_current_stock(cursor, product_id=5)
    cursor.close()
    connection.close()
    print(f"Stock after SAFE demo: {stock_after_safe} (should NOT be negative)")


if __name__ == "__main__":
    main()