# Warehouse Inventory Management System (PostgreSQL + Python)

A learning project that models a real warehouse inventory system using
PostgreSQL and raw SQL from Python. Built as a hands-on introduction to
relational databases — schema design, foreign keys, constraints, safe
data insertion, and reporting queries — using a domain (warehouse
stock) that mirrors real day-to-day work with goods receiving and
shipping.

## Tech stack

- **PostgreSQL 17** — relational database
- **psycopg2-binary** — raw PostgreSQL driver for Python (no ORM, on
  purpose — to see the real SQL being sent)
- **python-dotenv** — loads database credentials from a `.env` file,
  never hardcoded in code

## Database schema

Three tables:

- **categories** — lookup table (e.g. "Стройматериалы", "Крепёж")
- **products** — every item the warehouse handles: SKU, name, unit of
  measurement, and a `category_id` foreign key
- **stock_movements** — an append-only log of every IN/OUT event: which
  product, how many units, which direction, and a note. Current stock
  is never stored directly — it is always **calculated** from this
  history (`SUM(IN) - SUM(OUT)`), so it can never silently drift from
  the truth.

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

## Key SQL concepts covered

- `SERIAL PRIMARY KEY` and foreign keys (`REFERENCES`)
- `CHECK` constraints
- Parameterized queries (`%s` placeholders) to prevent SQL injection —
  never build SQL with f-strings
- `RETURNING id` to get auto-generated IDs back immediately
- `JOIN` (inner and `LEFT JOIN`) to combine data across tables
- `GROUP BY` with `SUM` / `COUNT` for aggregation
- `CASE WHEN ... THEN ... ELSE ... END` for conditional sums
- `COALESCE` to handle `NULL` from products with no movements yet
- `HAVING` to filter on an aggregated value

## Setup

1. Install PostgreSQL and create a database (e.g. `warehouse_db`).
2. Copy `.env.example` to `.env` and fill in your real database
   password. `.env` is gitignored and never uploaded.
3. Install dependencies: