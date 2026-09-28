"""
STEP 16: Inventory counts (инвентаризация) — reconciling the system's
number with what's physically on the shelf.

WHY THIS EXISTS:
No matter how careful everyone is, the database's calculated stock
can drift from physical reality over time — theft, damage nobody
logged, a scanning mistake, miscounted boxes. A real warehouse
periodically does инвентаризация: someone physically counts what's on
the shelf, and any difference from what the system says gets recorded
and corrected.

HOW THIS IS MODELED:
  - inventory_counts: one row per count session
  - inventory_count_items: system_quantity (before) vs counted_quantity
    (physically found), side by side, per product
  - apply_inventory_count(): for every item where the numbers DIFFER,
    inserts ONE correcting movement (IN or OUT) with a note explaining
    WHY — so the correction is fully traceable, not a silent jump.
"""

from step1_connect import get_connection


def ensure_inventory_tables(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_counts (
            id SERIAL PRIMARY KEY,
            store_id INTEGER NOT NULL REFERENCES stores(id),
            status VARCHAR(20) NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'applied')),
            started_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_count_items (
            id SERIAL PRIMARY KEY,
            inventory_count_id INTEGER NOT NULL REFERENCES inventory_counts(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            system_quantity NUMERIC(10, 2) NOT NULL,
            counted_quantity NUMERIC(10, 2) NOT NULL
        );
        """
    )


def get_physical_stock(cursor, product_id: int, store_id: int) -> float:
    cursor.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN movement_type = 'IN' THEN quantity ELSE -quantity END), 0)
        FROM stock_movements WHERE product_id = %s AND store_id = %s;
        """,
        (product_id, store_id),
    )
    return cursor.fetchone()[0]


def start_inventory_count(cursor, store_id: int, counted: dict) -> int:
    cursor.execute(
        "INSERT INTO inventory_counts (store_id) VALUES (%s) RETURNING id;",
        (store_id,),
    )
    count_id = cursor.fetchone()[0]

    for sku, counted_quantity in counted.items():
        cursor.execute("SELECT id FROM products WHERE sku = %s;", (sku,))
        product_id = cursor.fetchone()[0]
        system_quantity = get_physical_stock(cursor, product_id, store_id)
        cursor.execute(
            """
            INSERT INTO inventory_count_items (inventory_count_id, product_id, system_quantity, counted_quantity)
            VALUES (%s, %s, %s, %s);
            """,
            (count_id, product_id, system_quantity, counted_quantity),
        )
        diff = counted_quantity - system_quantity
        print(f"  {sku}: system says {system_quantity}, counted {counted_quantity} (diff: {diff:+})")

    print(f"  Inventory count #{count_id} started (status=open, nothing corrected yet).")
    return count_id


def apply_inventory_count(connection, count_id: int) -> bool:
    cursor = connection.cursor()
    cursor.execute(
        "SELECT status, store_id FROM inventory_counts WHERE id = %s FOR UPDATE;",
        (count_id,),
    )
    row = cursor.fetchone()
    if row is None:
        print(f"  REJECTED: no inventory count with id={count_id}.")
        connection.rollback()
        cursor.close()
        return False

    status, store_id = row
    if status != "open":
        print(f"  REJECTED: count #{count_id} is already '{status}'.")
        connection.rollback()
        cursor.close()
        return False

    cursor.execute(
        "SELECT product_id, system_quantity, counted_quantity FROM inventory_count_items WHERE inventory_count_id = %s;",
        (count_id,),
    )
    items = cursor.fetchall()

    corrections_made = 0
    for product_id, system_quantity, counted_quantity in items:
        diff = counted_quantity - system_quantity
        if diff == 0:
            continue
        movement_type = "IN" if diff > 0 else "OUT"
        cursor.execute(
            """
            INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (
                product_id,
                store_id,
                movement_type,
                abs(diff),
                f"Inventory count #{count_id} correction (system said {system_quantity}, counted {counted_quantity})",
            ),
        )
        corrections_made += 1

    cursor.execute(
        "UPDATE inventory_counts SET status = 'applied' WHERE id = %s;",
        (count_id,),
    )
    connection.commit()
    print(f"  OK: count #{count_id} applied — {corrections_made} correcting movement(s) created.")
    cursor.close()
    return True


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    print("Ensuring inventory count tables exist...")
    ensure_inventory_tables(cursor)
    connection.commit()

    print("\nStarting an inventory count at store 1 (someone physically counted the shelf)...")
    count_id = start_inventory_count(
        cursor,
        store_id=1,
        counted={"SKU-002": 3790, "SKU-003": 7505},
    )
    connection.commit()
    cursor.close()

    print(f"\nApplying inventory count #{count_id} (creates correcting movements)...")
    apply_inventory_count(connection, count_id)

    print(f"\nTrying to apply count #{count_id} AGAIN (should be rejected)...")
    apply_inventory_count(connection, count_id)

    connection.close()


if __name__ == "__main__":
    main()