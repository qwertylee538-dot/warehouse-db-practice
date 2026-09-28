"""
STEP 2: Create the database schema — categories, products, and stock
movements.

THE THREE TABLES, AND WHY THIS SHAPE:
  - categories: a small lookup table (e.g. "Building materials",
    "Fasteners", "Tools"). Just an id and a name.
  - products: every item the warehouse handles — SKU (article
    number), name, unit of measurement (pcs/kg/m), and a
    category_id that POINTS AT a row in categories, instead of
    storing the category name as text on every single product.
  - stock_movements: every time stock comes in or goes out — which
    product, how many units, which direction (IN or OUT), and when.
    This is the append-only log: instead of a single "current stock"
    number we could accidentally edit wrong, current stock is always
    CALCULATED from this history (see step4 for how).

FOREIGN KEYS — WHY products.category_id REFERENCES categories(id):
A foreign key tells PostgreSQL "this column's value must match an id
that actually exists in that other table". This makes it IMPOSSIBLE
to insert a product with category_id = 999 if no category with id 999
exists — the database itself rejects that at insert time, rather than
letting bad data slip in that some report only discovers later.

SERIAL / GENERATED ALWAYS AS IDENTITY:
Every table's `id` column auto-increments — PostgreSQL assigns 1, 2,
3... automatically as rows are inserted, so we never have to invent
IDs ourselves or worry about clashing with an existing one.

CHECK CONSTRAINT ON movement_type:
`movement_type` can only ever be the text 'IN' or 'OUT' — the CHECK
constraint enforces this at the database level, so a typo like 'in '
or 'inbound' is rejected immediately instead of silently corrupting
every report that later assumes only those two values exist.

WHY DROP TABLE IF EXISTS FIRST:
This script is meant to be safely re-run from scratch while you're
still learning and experimenting — dropping and recreating the tables
each time means you always start from a known, clean state. A real
production system would instead use "migrations" (versioned, incremental
schema changes) so existing data is never wiped — that's a topic for
a later step once there's real data worth preserving.
"""

from step1_connect import get_connection

# CASCADE on the DROP means "and also drop anything that depends on
# this table" (e.g. stock_movements depends on products). We drop in
# reverse order of creation anyway, but CASCADE is a safety net.
DROP_TABLES_SQL = """
DROP TABLE IF EXISTS stock_movements CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS categories CASCADE;
"""

CREATE_TABLES_SQL = """
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,      -- article / stock-keeping unit code
    name VARCHAR(200) NOT NULL,
    unit VARCHAR(20) NOT NULL DEFAULT 'pcs',  -- e.g. 'pcs', 'kg', 'm'
    category_id INTEGER NOT NULL REFERENCES categories(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE stock_movements (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    movement_type VARCHAR(3) NOT NULL CHECK (movement_type IN ('IN', 'OUT')),
    quantity NUMERIC(10, 2) NOT NULL CHECK (quantity > 0),
    note VARCHAR(300),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
"""


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    print("Dropping old tables (if any)...")
    cursor.execute(DROP_TABLES_SQL)

    print("Creating tables: categories, products, stock_movements...")
    cursor.execute(CREATE_TABLES_SQL)

    # Nothing is actually saved to the database until we commit — up
    # until this point, everything above happened in an uncommitted
    # transaction that could still be rolled back (undone).
    connection.commit()

    print("Done. Schema created successfully.")

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()