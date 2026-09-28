"""
STEP 9: Indexes — making lookups fast, and PROVING it with EXPLAIN ANALYZE.

WHAT AN INDEX IS:
Without an index, finding all movements for one product means
PostgreSQL reads through EVERY row in stock_movements and checks each
one — this is called a "Sequential Scan" (Seq Scan). That's fine for a
few dozen rows, but on a real warehouse table with millions of rows,
it becomes painfully slow. An index on a column is a separate, sorted
structure (like a book's index at the back) that lets PostgreSQL jump
straight to the matching rows instead of checking every single one —
this is an "Index Scan".

WHY THIS FILE ADDS A LOT OF FAKE DATA FIRST:
On our tiny sample table (barely 20 rows), PostgreSQL is actually
smart enough to decide a Seq Scan is just as fast as an Index Scan —
reading 20 rows takes microseconds either way, so an index wouldn't
prove anything. To see the REAL difference, this script inserts
20,000 extra throwaway movement rows first, so there's enough data for
the slow path to actually be slow.

EXPLAIN ANALYZE — READING A QUERY PLAN:
Putting "EXPLAIN ANALYZE" in front of any query makes PostgreSQL RUN
it for real and then print out exactly how it found the rows and how
long each step took, instead of returning the query's normal results.
We run the same query twice: once before creating the index (expect
"Seq Scan"), once after (expect "Index Scan"), and compare.
"""

import time

from step1_connect import get_connection


def add_bulk_test_data(cursor, connection, num_rows: int = 20000) -> None:
    cursor.execute(
        "SELECT COUNT(*) FROM stock_movements WHERE note = 'bulk test data for step9';"
    )
    already_there = cursor.fetchone()[0]
    if already_there >= num_rows:
        print(f"  Bulk test data already present ({already_there} rows) — skipping insert.")
        return

    print(f"  Inserting {num_rows} throwaway rows (this takes a few seconds)...")
    rows = [
        (
            (i % 6) + 1,
            1,
            "IN" if i % 2 == 0 else "OUT",
            1,
            "bulk test data for step9",
        )
        for i in range(num_rows)
    ]
    cursor.executemany(
        """
        INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note)
        VALUES (%s, %s, %s, %s, %s);
        """,
        rows,
    )
    connection.commit()
    print("  Done inserting bulk test data.")


def explain_lookup_by_product(cursor, product_id: int, label: str) -> None:
    print(f"\n--- EXPLAIN ANALYZE: find all movements for product_id={product_id} ({label}) ---")
    cursor.execute(
        "EXPLAIN ANALYZE SELECT * FROM stock_movements WHERE product_id = %s;",
        (product_id,),
    )
    for row in cursor.fetchall():
        print(" ", row[0])


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    print("Step A: making sure there's enough data to see a real difference...")
    add_bulk_test_data(cursor, connection)

    print("\nStep B: query plan BEFORE adding an index (expect 'Seq Scan')...")
    explain_lookup_by_product(cursor, product_id=3, label="no index yet")

    print("\nStep C: creating an index on stock_movements(product_id)...")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_stock_movements_product_id "
        "ON stock_movements (product_id);"
    )
    connection.commit()
    print("  Index created (or already existed).")

    print("\nStep D: query plan AFTER adding the index (expect 'Index Scan')...")
    explain_lookup_by_product(cursor, product_id=3, label="with index")

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()