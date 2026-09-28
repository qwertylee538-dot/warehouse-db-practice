"""
STEP 12: Customers, orders, and RESERVING stock.

WHY RESERVATIONS ARE A NEW IDEA:
So far, "current stock" has only ever meant "physically on the
shelf right now." But a real store also needs to answer a slightly
different question: "how much can I actually PROMISE to a NEW
customer?" If 10 drills are on the shelf but 4 of them are already
promised to someone else's order (paid for, waiting for pickup), you
can only sell 6 more — even though the shelf still physically holds 10.
That's the difference between:
  - physical stock  = SUM(IN) - SUM(OUT)                  (what we had before)
  - available stock = physical stock - SUM(active reservations) (new!)

HOW THIS IS MODELED:
  - customers: who's ordering
  - orders: one row per customer order, with a status
    ('reserved' / 'fulfilled' / 'cancelled')
  - order_items: which products, how many, per order (same
    one-to-many pattern as purchase_order_items in step11)

RESERVATIONS DON'T TOUCH stock_movements AT ALL:
Placing an order does NOT insert an OUT movement — nothing physically
leaves the shelf yet. It only creates an `orders` row with status
'reserved'. The stock only actually leaves when fulfill_order() runs,
which inserts the real OUT movements (same pattern as step11's
receive_purchase_order creating IN movements) and flips the order to
'fulfilled'.
"""

from step1_connect import get_connection

CUSTOMERS = [
    ("Иванов И.И.", "+7 901 222-33-44"),
    ("ООО СтройМонтаж", "+7 901 555-66-77"),
]


def ensure_customer_tables(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id SERIAL PRIMARY KEY,
            name VARCHAR(150) NOT NULL UNIQUE,
            phone VARCHAR(30)
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            store_id INTEGER NOT NULL REFERENCES stores(id),
            status VARCHAR(20) NOT NULL DEFAULT 'reserved'
                CHECK (status IN ('reserved', 'fulfilled', 'cancelled')),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS order_items (
            id SERIAL PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity NUMERIC(10, 2) NOT NULL CHECK (quantity > 0)
        );
        """
    )


def insert_customers(cursor) -> dict:
    name_to_id = {}
    for name, phone in CUSTOMERS:
        cursor.execute(
            "INSERT INTO customers (name, phone) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING;",
            (name, phone),
        )
        cursor.execute("SELECT id FROM customers WHERE name = %s;", (name,))
        name_to_id[name] = cursor.fetchone()[0]
    return name_to_id


def get_physical_stock(cursor, product_id: int, store_id: int) -> float:
    cursor.execute(
        """
        SELECT COALESCE(
            SUM(CASE WHEN movement_type = 'IN' THEN quantity ELSE -quantity END), 0
        )
        FROM stock_movements
        WHERE product_id = %s AND store_id = %s;
        """,
        (product_id, store_id),
    )
    return cursor.fetchone()[0]


def get_reserved_quantity(cursor, product_id: int, store_id: int) -> float:
    cursor.execute(
        """
        SELECT COALESCE(SUM(oi.quantity), 0)
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        WHERE oi.product_id = %s AND o.store_id = %s AND o.status = 'reserved';
        """,
        (product_id, store_id),
    )
    return cursor.fetchone()[0]


def available_stock(cursor, product_id: int, store_id: int) -> float:
    physical = get_physical_stock(cursor, product_id, store_id)
    reserved = get_reserved_quantity(cursor, product_id, store_id)
    return physical - reserved


def place_order(connection, customer_id: int, store_id: int, items: list):
    cursor = connection.cursor()

    resolved_items = []
    for sku, quantity in items:
        cursor.execute("SELECT id FROM products WHERE sku = %s FOR UPDATE;", (sku,))
        row = cursor.fetchone()
        if row is None:
            print(f"  REJECTED: unknown SKU '{sku}'.")
            connection.rollback()
            cursor.close()
            return None
        product_id = row[0]

        available = available_stock(cursor, product_id, store_id)
        if quantity > available:
            print(
                f"  REJECTED: only {available} of '{sku}' available "
                f"(some may already be reserved by other orders)."
            )
            connection.rollback()
            cursor.close()
            return None
        resolved_items.append((product_id, quantity))

    cursor.execute(
        "INSERT INTO orders (customer_id, store_id) VALUES (%s, %s) RETURNING id;",
        (customer_id, store_id),
    )
    order_id = cursor.fetchone()[0]
    for product_id, quantity in resolved_items:
        cursor.execute(
            "INSERT INTO order_items (order_id, product_id, quantity) VALUES (%s, %s, %s);",
            (order_id, product_id, quantity),
        )

    connection.commit()
    print(f"  OK: order #{order_id} placed and reserved ({len(resolved_items)} item(s)).")
    cursor.close()
    return order_id


def fulfill_order(connection, order_id: int) -> bool:
    cursor = connection.cursor()
    cursor.execute(
        "SELECT status, store_id FROM orders WHERE id = %s FOR UPDATE;",
        (order_id,),
    )
    row = cursor.fetchone()
    if row is None:
        print(f"  REJECTED: no order with id={order_id}.")
        connection.rollback()
        cursor.close()
        return False

    status, store_id = row
    if status != "reserved":
        print(f"  REJECTED: order #{order_id} is '{status}', not 'reserved'.")
        connection.rollback()
        cursor.close()
        return False

    cursor.execute(
        "SELECT product_id, quantity FROM order_items WHERE order_id = %s;",
        (order_id,),
    )
    items = cursor.fetchall()
    for product_id, quantity in items:
        cursor.execute(
            """
            INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note)
            VALUES (%s, %s, 'OUT', %s, %s);
            """,
            (product_id, store_id, quantity, f"Fulfilled order #{order_id}"),
        )
    cursor.execute("UPDATE orders SET status = 'fulfilled' WHERE id = %s;", (order_id,))
    connection.commit()
    print(f"  OK: order #{order_id} fulfilled — {len(items)} stock movement(s) created.")
    cursor.close()
    return True


def stock_summary(cursor, sku: str, store_id: int) -> None:
    cursor.execute("SELECT id, name FROM products WHERE sku = %s;", (sku,))
    product_id, name = cursor.fetchone()
    physical = get_physical_stock(cursor, product_id, store_id)
    reserved = get_reserved_quantity(cursor, product_id, store_id)
    print(f"  {sku} ({name}) at store {store_id}: physical={physical}, reserved={reserved}, available={physical - reserved}")


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    print("Ensuring customer/order tables exist...")
    ensure_customer_tables(cursor)
    connection.commit()

    print("Inserting sample customers...")
    customer_ids = insert_customers(cursor)
    connection.commit()
    customer_id = customer_ids["Иванов И.И."]

    print("\nStock before any orders:")
    stock_summary(cursor, "SKU-005", store_id=1)
    cursor.close()

    print("\nPlacing an order (reserves stock, does NOT touch stock_movements)...")
    order_id = place_order(connection, customer_id=customer_id, store_id=1, items=[("SKU-005", 1)])

    cursor = connection.cursor()
    print("\nStock after reserving (physical unchanged, available drops):")
    stock_summary(cursor, "SKU-005", store_id=1)
    cursor.close()

    if order_id is not None:
        print(f"\nFulfilling order #{order_id} (this creates the real OUT movement)...")
        fulfill_order(connection, order_id)

    cursor = connection.cursor()
    print("\nStock after fulfilling (physical drops too now):")
    stock_summary(cursor, "SKU-005", store_id=1)
    cursor.close()

    connection.close()


if __name__ == "__main__":
    main()