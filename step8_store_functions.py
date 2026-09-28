"""
STEP 8: More store-aware functions — comparison, low stock, top
products (window functions), and transferring stock between stores.

NEW CONCEPT: WINDOW FUNCTIONS (RANK() OVER (PARTITION BY ...))
GROUP BY (used in earlier steps) COLLAPSES many rows into one row per
group — you lose the individual rows, only the summary remains.
A window function is different: it calculates something ACROSS a
group of rows (a "window"), but keeps every row visible. RANK() OVER
(PARTITION BY store_name ORDER BY total_moved DESC) reads as: "within
each store (that's the PARTITION — the window), rank every product by
how much it moved, from busiest (rank 1) downward — but still show me
every row, not just one summary row per store." This is exactly what
you need for "top N per group" questions, which plain GROUP BY cannot
answer on its own.

transfer_stock() REUSES step5's transactions and step6's locking:
Moving stock from one store to another is really TWO writes that must
happen together (an OUT at the source, an IN at the destination) — if
only one succeeded, stock would either vanish or be duplicated out of
nowhere. So, just like step5, we wrap both writes in one transaction
and roll back entirely if anything is wrong (not enough stock at the
source, or an invalid store/product). Just like step6, we lock the
product row first with SELECT ... FOR UPDATE, so two simultaneous
transfers of the same product can't both read stale stock numbers.
"""

from step1_connect import get_connection


def get_current_stock_for_store(cursor, product_id: int, store_id: int) -> float:
    cursor.execute(
        """
        SELECT COALESCE(
            SUM(CASE WHEN movement_type = 'IN' THEN quantity ELSE -quantity END),
            0
        )
        FROM stock_movements
        WHERE product_id = %s AND store_id = %s;
        """,
        (product_id, store_id),
    )
    return cursor.fetchone()[0]


def print_rows(cursor, headers: list) -> None:
    rows = cursor.fetchall()
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, value in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(value)))
    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print("-" * len(header_line))
    for row in rows:
        print("  ".join(str(value).ljust(col_widths[i]) for i, value in enumerate(row)))
    print()


def compare_stores(cursor) -> None:
    """One row per store: how many distinct products it has stocked,
    and the total units currently on its shelves, combined.
    """
    print("=== Store comparison ===")
    cursor.execute(
        """
        SELECT
            s.name AS store,
            COUNT(DISTINCT p.id) FILTER (WHERE m.id IS NOT NULL) AS distinct_products,
            COALESCE(SUM(CASE WHEN m.movement_type = 'IN' THEN m.quantity ELSE -m.quantity END), 0) AS total_units_in_stock
        FROM stores s
        LEFT JOIN stock_movements m ON m.store_id = s.id
        LEFT JOIN products p ON p.id = m.product_id
        GROUP BY s.name
        ORDER BY s.name;
        """
    )
    print_rows(cursor, ["Store", "Distinct products", "Total units in stock"])


def low_stock_by_store(cursor, threshold: int = 50) -> None:
    """Every (store, product) combination whose stock in THAT store is
    below the threshold — including 0, which means "not stocked there
    at all", a very real reordering signal.
    """
    print(f"=== Low stock (< {threshold}) per store ===")
    cursor.execute(
        """
        SELECT
            s.name AS store,
            p.sku,
            p.name AS product,
            COALESCE(SUM(CASE WHEN m.movement_type = 'IN' THEN m.quantity ELSE -m.quantity END), 0) AS current_stock
        FROM stores s
        CROSS JOIN products p
        LEFT JOIN stock_movements m ON m.product_id = p.id AND m.store_id = s.id
        GROUP BY s.name, p.sku, p.name
        HAVING COALESCE(SUM(CASE WHEN m.movement_type = 'IN' THEN m.quantity ELSE -m.quantity END), 0) < %s
        ORDER BY s.name, current_stock ASC;
        """,
        (threshold,),
    )
    print_rows(cursor, ["Store", "SKU", "Product", "Current stock"])


def top_products_by_store(cursor, top_n: int = 2) -> None:
    """The busiest products (by total quantity moved, IN + OUT) in
    EACH store, using a window function to rank within each store
    without collapsing the per-product rows the way GROUP BY would.
    """
    print(f"=== Top {top_n} busiest products per store (by volume moved) ===")
    cursor.execute(
        """
        WITH volume_per_store_product AS (
            SELECT
                s.name AS store,
                p.sku,
                p.name AS product,
                COALESCE(SUM(m.quantity), 0) AS total_moved
            FROM stores s
            JOIN stock_movements m ON m.store_id = s.id
            JOIN products p ON p.id = m.product_id
            GROUP BY s.name, p.sku, p.name
        ),
        ranked AS (
            SELECT
                *,
                RANK() OVER (PARTITION BY store ORDER BY total_moved DESC) AS rank_in_store
            FROM volume_per_store_product
        )
        SELECT store, sku, product, total_moved, rank_in_store
        FROM ranked
        WHERE rank_in_store <= %s
        ORDER BY store, rank_in_store;
        """,
        (top_n,),
    )
    print_rows(cursor, ["Store", "SKU", "Product", "Total moved", "Rank"])


def transfer_stock(connection, product_id: int, from_store_id: int, to_store_id: int, quantity: float, note: str) -> bool:
    """Move `quantity` of one product from one store to another, as a
    single all-or-nothing operation. Returns True on success, False if
    rejected (in which case nothing at all was changed).
    """
    cursor = connection.cursor()

    cursor.execute("SELECT id FROM products WHERE id = %s FOR UPDATE;", (product_id,))
    if cursor.fetchone() is None:
        print(f"  REJECTED: no product with id={product_id}.")
        connection.rollback()
        cursor.close()
        return False

    source_stock = get_current_stock_for_store(cursor, product_id, from_store_id)
    if quantity > source_stock:
        print(
            f"  REJECTED: source store only has {source_stock}, "
            f"cannot transfer {quantity}."
        )
        connection.rollback()
        cursor.close()
        return False

    cursor.execute(
        """
        INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note)
        VALUES (%s, %s, 'OUT', %s, %s);
        """,
        (product_id, from_store_id, quantity, f"Transfer out — {note}"),
    )
    cursor.execute(
        """
        INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note)
        VALUES (%s, %s, 'IN', %s, %s);
        """,
        (product_id, to_store_id, quantity, f"Transfer in — {note}"),
    )

    connection.commit()
    print(f"  OK: transferred {quantity} of product id={product_id} "
          f"from store {from_store_id} to store {to_store_id}.")
    cursor.close()
    return True


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    compare_stores(cursor)
    low_stock_by_store(cursor, threshold=50)
    top_products_by_store(cursor, top_n=2)

    cursor.close()

    print("=== Demo transfer: 1 Bosch drill, store 1 -> store 2 ===")
    transfer_stock(
        connection,
        product_id=5,
        from_store_id=1,
        to_store_id=2,
        quantity=1,
        note="Demo rebalance between stores",
    )

    cursor = connection.cursor()
    print()
    compare_stores(cursor)
    cursor.close()

    connection.close()


if __name__ == "__main__":
    main()