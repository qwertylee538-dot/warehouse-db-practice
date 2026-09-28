"""
STEP 4: Real queries — turning raw movement history into useful
reports.

THE CORE IDEA: CURRENT STOCK IS *CALCULATED*, NOT STORED.
We never stored a "current_quantity" column anywhere. Instead,
current stock for any product is always:
    (total of all IN movements) - (total of all OUT movements)
This is a deliberate design choice: if we stored a running total
directly, every insert would need to remember to update it too, and
any bug or manual data fix could make that number drift away from
what the movement history actually shows. Calculating it fresh from
the log is slower but can never silently go wrong.

JOIN — COMBINING ROWS FROM DIFFERENT TABLES:
Our data is split across three tables on purpose (see step2). A JOIN
is how SQL puts related rows back together for a query — e.g. "match
each product to its category name" by matching products.category_id
to categories.id. Without a JOIN, you'd only ever see raw category_id
numbers instead of readable names.

GROUP BY + aggregate functions (SUM, COUNT):
GROUP BY collapses many rows into one row per group — e.g. "one row
per product" instead of one row per individual movement — and SUM()
adds up a column across all the rows in each group. This is exactly
how "total stock per product" is computed from a list of individual
IN/OUT events.

CASE WHEN — CONDITIONAL LOGIC INSIDE SQL:
`SUM(CASE WHEN movement_type = 'IN' THEN quantity ELSE 0 END)` reads
as: "for each row, if it's an IN movement use its quantity, otherwise
use 0 — then add all of those up." This is how we get separate totals
for IN and OUT out of a single column that mixes both.
"""

from step1_connect import get_connection


def print_table(cursor, headers: list) -> None:
    """Print whatever the last executed query returned as a simple
    aligned table. Just formatting — no new SQL concepts here.
    """
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


def current_stock_report(cursor) -> None:
    """For every product: total IN, total OUT, and current stock
    (IN - OUT), joined with its category name.
    """
    print("=== Current stock per product ===")
    cursor.execute(
        """
        SELECT
            p.sku,
            p.name,
            c.name AS category,
            p.unit,
            COALESCE(SUM(CASE WHEN m.movement_type = 'IN' THEN m.quantity ELSE 0 END), 0) AS total_in,
            COALESCE(SUM(CASE WHEN m.movement_type = 'OUT' THEN m.quantity ELSE 0 END), 0) AS total_out,
            COALESCE(SUM(CASE WHEN m.movement_type = 'IN' THEN m.quantity ELSE -m.quantity END), 0) AS current_stock
        FROM products p
        JOIN categories c ON c.id = p.category_id
        LEFT JOIN stock_movements m ON m.product_id = p.id
        GROUP BY p.id, p.sku, p.name, c.name, p.unit
        ORDER BY p.sku;
        """
    )
    print_table(cursor, ["SKU", "Name", "Category", "Unit", "IN", "OUT", "Current stock"])


def low_stock_report(cursor, threshold: int = 100) -> None:
    """Products whose current stock has fallen below a threshold —
    the kind of report a warehouse actually checks every morning to
    know what needs reordering.
    """
    print(f"=== Products below {threshold} units in stock ===")
    cursor.execute(
        """
        SELECT
            p.sku,
            p.name,
            p.unit,
            COALESCE(SUM(CASE WHEN m.movement_type = 'IN' THEN m.quantity ELSE -m.quantity END), 0) AS current_stock
        FROM products p
        LEFT JOIN stock_movements m ON m.product_id = p.id
        GROUP BY p.id, p.sku, p.name, p.unit
        HAVING COALESCE(SUM(CASE WHEN m.movement_type = 'IN' THEN m.quantity ELSE -m.quantity END), 0) < %s
        ORDER BY current_stock ASC;
        """,
        (threshold,),
    )
    print_table(cursor, ["SKU", "Name", "Unit", "Current stock"])


def movements_by_category(cursor) -> None:
    """Total quantity moved (in + out combined) grouped by category —
    which categories are the most active in the warehouse.
    """
    print("=== Total movement volume by category ===")
    cursor.execute(
        """
        SELECT
            c.name AS category,
            COUNT(m.id) AS movement_count,
            COALESCE(SUM(m.quantity), 0) AS total_quantity_moved
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.id
        LEFT JOIN stock_movements m ON m.product_id = p.id
        GROUP BY c.name
        ORDER BY total_quantity_moved DESC;
        """
    )
    print_table(cursor, ["Category", "Movement count", "Total quantity moved"])


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    current_stock_report(cursor)
    low_stock_report(cursor, threshold=100)
    movements_by_category(cursor)

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()