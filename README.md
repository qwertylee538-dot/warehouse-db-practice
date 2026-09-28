# Warehouse Inventory Management System (PostgreSQL + Python)

A learning project that models a real multi-store retail/warehouse
system using PostgreSQL and raw SQL from Python — schema design,
transactions, locking, indexing, purchase orders, customer orders with
reservations, price history, discounts, employee shifts, regulatory
tracking (EGAIS/Mercury-style), a consolidated dashboard, and a
secured web API with real authentication.

## Tech stack

- **PostgreSQL 17** — relational database
- **psycopg2-binary** — raw PostgreSQL driver (no ORM, on purpose)
- **python-dotenv** — loads database credentials from `.env`
- **FastAPI + Uvicorn** — the secured web API (step23)
- **PyJWT** — signs and verifies login tokens
- **passlib + bcrypt** — one-way password hashing (real passwords are
  never stored)

## Project steps

| File | What it does |
|---|---|
| `step1_connect.py` | Connects to PostgreSQL, prints the server version |
| `step2_create_tables.py` | Schema: `categories`, `products`, `stock_movements` |
| `step3_insert_data.py` | Sample data via parameterized queries |
| `step4_queries.py` | Reporting: current stock, low-stock alerts, movement volume |
| `step5_transactions.py` | Transactions with rollback (safe shipping) |
| `step6_locking.py` | `SELECT ... FOR UPDATE`: demonstrates and fixes a real race condition |
| `step7_stores.py` | Multi-store support via `store_id` (schema migration) |
| `step8_store_functions.py` | Per-store reports, window functions, `transfer_stock()` |
| `step9_indexes.py` | Indexes + `EXPLAIN ANALYZE` proof |
| `step10_prices.py` | Product prices, inventory value reports |
| `step11_suppliers.py` | Suppliers and purchase orders (pending -> received lifecycle) |
| `step12_customer_orders.py` | Customers, orders, and stock **reservation** |
| `step13_price_history.py` | Price history instead of one overwritten price |
| `step14_employees.py` | Employees, `employee_id` on every movement, activity report |
| `step15_barcodes.py` | Barcodes and scan-to-find, like a handheld terminal |
| `step16_inventory_count.py` | Инвентаризация: reconciling counted vs system stock |
| `step17_write_offs.py` | Write-offs (брак/порча) as a distinct movement type |
| `step18_returns.py` | Customer returns, capped at what was actually bought |
| `step19_discounts.py` | Time-boxed discounts/promotions |
| `step20_shifts.py` | Opening/closing employee shifts, per-shift reports |
| `step21_regulatory_tracking.py` | EGAIS/Mercury-style unique government marks |
| `step22_dashboard.py` | Consolidated dashboard reusing every report above |
| `step23_web_api.py` | **Secured FastAPI web service**: password hashing, JWT login, protected endpoints |
| `cli.py` | Interactive terminal menu for the core reports |
| `fix_step9_data.py`, `fix_step18_data.py`, `fix_step18_data_v2.py` | One-off data corrections for bugs found and fixed along the way |

## Key concepts covered

- Foreign keys, `CHECK` constraints, parameterized queries (SQL-injection-safe)
- `JOIN`, `GROUP BY`, `CASE WHEN`, `COALESCE`, `HAVING`
- **Transactions** (`COMMIT`/`ROLLBACK`) and **row locking** (`SELECT ... FOR UPDATE`)
- **Schema migrations**: `ALTER TABLE ADD COLUMN`, widening `CHECK` constraints and column types
- **Window functions** (`RANK() OVER (PARTITION BY ...)`) and **CTEs**
- **Indexes** and reading a query plan with `EXPLAIN ANALYZE`
- **Document lifecycles** (pending -> received/fulfilled, with locking to prevent double-processing)
- **Stock reservation** vs physical stock (available vs on-shelf)
- **Regulatory-style unique-mark tracking** (EGAIS/Mercury), preventing double-use
- **Password hashing** (bcrypt) and **JWT-based authentication** on a real web API

## What this project deliberately does NOT include

A production point-of-sale deployment needs several things that go
beyond code alone: a certified fiscal cash register (54-ФЗ), a real
registered connection to EGAIS/Mercury (requires legal registration
and crypto keys), a polished UI for non-technical staff, and hosting/
backups/monitoring. This project's job is to demonstrate the correct
underlying architecture and logic — the reusable foundation those
integrations would sit on top of.

## Setup

1. Install PostgreSQL and create a database (e.g. `warehouse_db`).
2. Copy `.env.example` to `.env` and fill in your real database password.
3. `pip install -r requirements.txt`
4. Run the steps in order, `python step1_connect.py` through `python step22_dashboard.py`.
5. Explore interactively: `python cli.py`
6. Run the secured web API: `uvicorn step23_web_api:app --reload`, then
   open `http://127.0.0.1:8000/docs`. Demo login: `anna` /
   `demo-password-123`.

## Sample output

```
=== Products below 100 units in stock ===
SKU        Name                       Unit  Current stock
SKU-005    Перфоратор Bosch GBH 2-26  pcs   12.00
```