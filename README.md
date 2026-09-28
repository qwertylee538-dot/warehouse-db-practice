# Warehouse Inventory Management System (PostgreSQL + Python)

A learning project that models a real multi-store warehouse inventory
system using PostgreSQL and raw SQL from Python. Built as a hands-on
introduction to relational databases — schema design, foreign keys,
constraints, transactions, locking, indexing, and reporting — using a
domain (warehouse stock) that mirrors real day-to-day work with goods
receiving and shipping.

## Tech stack

- **PostgreSQL 17** — relational database
- **psycopg2-binary** — raw PostgreSQL driver for Python (no ORM, on
  purpose — to see the real SQL being sent)
- **python-dotenv** — loads database credentials from a `.env` file,
  never hardcoded in code

## Database schema

- **categories** — lookup table (e.g. "Стройматериалы", "Крепёж")
- **products** — every item the warehouse handles: SKU, name, unit of
  measurement, price, and a `category_id` foreign key
- **stores** — each physical shop/warehouse location
- **stock_movements** — an append-only log of every IN/OUT event: which
  product, which store, how many units, which direction, and a note.
  Current stock is never stored directly — it is always **calculated**
  from this history (`SUM(IN) - SUM(OUT)`), so it can never silently
  drift from the truth. Each store's stock is independent, computed by
  filtering this same table on `store_id`.

Foreign keys and `CHECK` constraints (e.g. `movement_type IN ('IN',
'OUT')`, `quantity > 0`) enforce data correctness at the database
level, not just in Python code.

## Project steps

| File | What it does |
|---|---|
| `step1_connect.py` | Connects to PostgreSQL from Python, prints the server version |
| `step2_create_tables.py` | Creates the schema: `categories`, `products`, `stock_movements` |
| `step3_insert_data.py` | Inserts sample data using parameterized queries (SQL-injection-safe) |
| `step4_queries.py` | Reporting queries: current stock per product, low-stock alerts, movement volume by category |
| `step5_transactions.py` | Transactions: safely shipping stock with rollback if it would go negative |
| `step6_locking.py` | Row locking (`SELECT ... FOR UPDATE`): demonstrates and fixes a real race condition |
| `step7_stores.py` | Adds multi-store support (a `stores` table + `store_id` column) via a safe schema migration |
| `step8_store_functions.py` | Per-store reports (comparison, low stock, top products via window functions) and `transfer_stock()` between stores |
| `step9_indexes.py` | Adds an index and proves the speedup with `EXPLAIN ANALYZE` |
| `step10_prices.py` | Adds product prices and inventory-value reports |
| `cli.py` | Interactive menu tying every report into one runnable application |

## Key SQL / database concepts covered

- `SERIAL PRIMARY KEY` and foreign keys (`REFERENCES`)
- `CHECK` constraints
- Parameterized queries (`%s` placeholders) to prevent SQL injection —
  never build SQL with f-strings
- `RETURNING id` to get auto-generated IDs back immediately
- `JOIN` (inner, `LEFT JOIN`, `CROSS JOIN`) to combine data across tables
- `GROUP BY` with `SUM` / `COUNT` for aggregation
- `CASE WHEN ... THEN ... ELSE ... END` for conditional sums
- `COALESCE` to handle `NULL` from products with no movements yet
- `HAVING` to filter on an aggregated value
- **Transactions** (`COMMIT` / `ROLLBACK`) for all-or-nothing operations
- **Row locking** (`SELECT ... FOR UPDATE`) to prevent race conditions
  under concurrent access
- **Schema migrations** (`ALTER TABLE`, `information_schema` checks) to
  evolve a schema without losing existing data
- **Window functions** (`RANK() OVER (PARTITION BY ...)`) for
  "top N per group" queries that `GROUP BY` alone can't answer
- **CTEs** (`WITH ... AS`) for breaking a