"""
STEP 11: Suppliers and purchase orders.

THE NEW IDEA: A DOCUMENT WITH A LIFECYCLE, NOT JUST A MOVEMENT.
Every earlier step treated "receiving stock" as one instant action —
call a function, an IN movement appears immediately. In real life,
that's not how it works: you first PLACE an order with a supplier
("please send us 500 bags of cement"), and only DAYS LATER, when the
truck actually arrives and you've counted the boxes, does the stock
physically exist on your shelf. Those are two separate real-world
events, so we model them as two separate database actions:
  1. create_purchase_order()  -> a document with status 'pending'
  2. receive_purchase_order() -> only THIS step creates real
     stock_movements ('IN' rows), and only once, ever, per order

THREE NEW TABLES:
  - suppliers: who you buy from
  - purchase_orders: one row per order — which supplier, which store
    it's headed to, and its status ('pending' / 'received' /
    'cancelled')
  - purchase_order_items: the line items of one order (which products,
    how many, at what price) — a purchase order can contain several
    different products, so this needs its own table (one order ->
    many item rows), the same one-to-many pattern as
    products -> stock_movements.

WHY receive_purchase_order() CHECKS THE STATUS FIRST (AND LOCKS THE ROW):
Without a check, calling "receive" twice by accident would create the
stock TWICE — the warehouse would think it got 500 bags of cement when
really only one truck ever arrived. We use SELECT ... FOR UPDATE on
the purchase_orders row (same locking idea as step6/step8) so that
even two people clicking "receive" at almost the same moment can't
both succeed — whichever gets there first locks the row and flips the
status to 'received'; the second one then sees the updated status and
is safely rejected.
"""

from step1_connect import get_connection

SUPPLIERS = [
    ("ООО СтройПоставка", "+7 900 111-22-33"),
    ("ИП Крепёж-Сервис", "+7 900 444-55-66"),
]


def ensure_supplier_tables(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            id SERIAL PRIMARY KEY,
            name VARCHAR(150) NOT NULL UNIQUE,
            phone VARCHAR(30)
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id SERIAL PRIMARY KEY,
            supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
            store_id INTEGER NOT NULL REFERENCES stores(id),
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'received', 'cancelled')),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_order_items (
            id SERIAL PRIMARY KEY,
            purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity NUMERIC(10, 2) NOT NULL CHECK (quantity > 0),
            unit_price NUMERIC(10, 2) NOT NULL
        );
        """
    )


def insert_suppliers(cursor) -> dict:
    name_to_id = {}
    for name, phone in SUPPLIERS:
        cursor.execute(
            "INSERT INTO suppliers (name, phone) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING;",
            (name, phone),
        )
        cursor.execute("SELECT id FROM suppliers WHERE name = %s;", (name,))
        name_to_id[name] = cursor.fetchone()[0]
    return name_to_id


def create_purchase_order(cursor, supplier_id: int, store_id: int, items: list) -> int:
    cursor.execute(
        "INSERT INTO purchase_orders (supplier_id, store_id) VALUES (%s, %s) RETURNING id;",
        (supplier_id, store_id),
    )
    order_id = cursor.fetchone()[0]

    for sku, quantity, unit_price in items:
        cursor.execute("SELECT id FROM products WHERE sku = %s;", (sku,))
        product_id = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO purchase_order_items (purchase_order_id, product_id, quantity, unit_price)
            VALUES (%s, %s, %s, %s);
            """,
            (order_id, product_id, quantity, unit_price),
        )
    print(f"  Created purchase order #{order_id} with {len(items)} line item(s), status=pending.")
    return order_id


def receive_purchase_order(connection, order_id: int) -> bool:
    cursor = connection.cursor()

    cursor.execute(
        "SELECT status, store_id FROM purchase_orders WHERE id = %s FOR UPDATE;",
        (order_id,),
    )
    row = cursor.fetchone()
    if row is None:
        print(f"  REJECTED: no purchase order with id={order_id}.")
        connection.rollback()
        cursor.close()
        return False

    status, store_id = row
    if status != "pending":
        print(f"  REJECTED: order #{order_id} is already '{status}', not 'pending'.")
        connection.rollback()
        cursor.close()
        return False

    cursor.execute(
        "SELECT product_id, quantity FROM purchase_order_items WHERE purchase_order_id = %s;",
        (order_id,),
    )
    items = cursor.fetchall()

    for product_id, quantity in items:
        cursor.execute(
            """
            INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note)
            VALUES (%s, %s, 'IN', %s, %s);
            """,
            (product_id, store_id, quantity, f"Received purchase order #{order_id}"),
        )

    cursor.execute(
        "UPDATE purchase_orders SET status = 'received' WHERE id = %s;",
        (order_id,),
    )
    connection.commit()
    print(f"  OK: order #{order_id} received — {len(items)} stock movement(s) created.")
    cursor.close()
    return True


def list_purchase_orders(cursor) -> None:
    print("\n=== Purchase orders ===")
    cursor.execute(
        """
        SELECT po.id, s.name AS supplier, st.name AS store, po.status, po.created_at
        FROM purchase_orders po
        JOIN suppliers s ON s.id = po.supplier_id
        JOIN stores st ON st.id = po.store_id
        ORDER BY po.id;
        """
    )
    rows = cursor.fetchall()
    headers = ["ID", "Supplier", "Store", "Status", "Created at"]
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

    print("Ensuring supplier/purchase-order tables exist...")
    ensure_supplier_tables(cursor)
    connection.commit()

    print("Inserting sample suppliers...")
    supplier_ids = insert_suppliers(cursor)
    connection.commit()
    supplier_id = supplier_ids["ООО СтройПоставка"]

    print("\nCreating a purchase order (status: pending, no stock yet)...")
    order_id = create_purchase_order(
        cursor,
        supplier_id=supplier_id,
        store_id=1,
        items=[("SKU-001", 100, 340.00), ("SKU-006", 50, 44.00)],
    )
    connection.commit()

    list_purchase_orders(cursor)
    cursor.close()

    print(f"\nReceiving purchase order #{order_id} (this should create stock)...")
    receive_purchase_order(connection, order_id)

    print(f"\nTrying to receive purchase order #{order_id} AGAIN (should be rejected)...")
    receive_purchase_order(connection, order_id)

    cursor = connection.cursor()
    list_purchase_orders(cursor)
    cursor.close()

    connection.close()


if __name__ == "__main__":
    main()