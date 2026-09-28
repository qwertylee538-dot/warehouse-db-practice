"""
STEP 22: Dashboard — one consolidated view pulling together reports
from across the whole project, the way a manager's home screen in 1C
shows several different reports at a glance instead of making you dig
through separate menus.

WHY THIS FILE HAS BARELY ANY NEW SQL:
This is deliberately NOT a new set of queries — it's a demonstration
that once you've built well-organized, reusable functions, a
"dashboard" is mostly just CALLING them together with clear section
headers.
"""

from step1_connect import get_connection
from step4_queries import current_stock_report, low_stock_report
from step8_store_functions import compare_stores
from step10_prices import inventory_value_by_store, most_valuable_products
from step14_employees import employee_activity_report
from step17_write_offs import write_off_report
from step18_returns import returns_report
from step19_discounts import effective_price
from step21_regulatory_tracking import tracking_report


def section(title: str) -> None:
    print("\n" + "#" * 60)
    print(f"# {title}")
    print("#" * 60)


def active_discounts_summary(cursor) -> None:
    section("ACTIVE DISCOUNTS RIGHT NOW")
    cursor.execute(
        """
        SELECT p.sku, p.name
        FROM discounts d
        JOIN products p ON p.id = d.product_id
        WHERE d.start_date <= CURRENT_DATE AND d.end_date >= CURRENT_DATE;
        """
    )
    rows = cursor.fetchall()
    if not rows:
        print("  No active discounts today.")
        return
    for sku, name in rows:
        cursor.execute("SELECT id FROM products WHERE sku = %s;", (sku,))
        product_id = cursor.fetchone()[0]
        price, discount = effective_price(cursor, product_id)
        print(f"  {sku} '{name}': {price} RUB (discount: {discount})")


def open_shifts_summary(cursor) -> None:
    section("OPEN SHIFTS RIGHT NOW")
    cursor.execute(
        """
        SELECT e.full_name, s.store_id, s.opened_at
        FROM shifts s
        JOIN employees e ON e.id = s.employee_id
        WHERE s.closed_at IS NULL;
        """
    )
    rows = cursor.fetchall()
    if not rows:
        print("  No open shifts right now.")
        return
    for full_name, store_id, opened_at in rows:
        print(f"  {full_name} — store {store_id}, opened {opened_at}")


def pending_purchase_orders_summary(cursor) -> None:
    section("PENDING PURCHASE ORDERS (awaiting delivery)")
    cursor.execute(
        """
        SELECT po.id, s.name
        FROM purchase_orders po
        JOIN suppliers s ON s.id = po.supplier_id
        WHERE po.status = 'pending';
        """
    )
    rows = cursor.fetchall()
    if not rows:
        print("  Nothing pending.")
        return
    for order_id, supplier in rows:
        print(f"  Order #{order_id} from {supplier}")


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    section("STOCK OVERVIEW (all stores)")
    current_stock_report(cursor)

    section("LOW STOCK ALERTS")
    low_stock_report(cursor, threshold=100)

    section("STORE COMPARISON")
    compare_stores(cursor)

    section("INVENTORY VALUE")
    inventory_value_by_store(cursor)
    most_valuable_products(cursor, top_n=3)

    active_discounts_summary(cursor)

    section("EMPLOYEE ACTIVITY")
    employee_activity_report(cursor)

    open_shifts_summary(cursor)

    pending_purchase_orders_summary(cursor)

    section("LOSSES: WRITE-OFFS")
    write_off_report(cursor)

    section("RETURNS")
    returns_report(cursor)

    section("REGULATORY TRACKING (EGAIS/Mercury-style marks)")
    tracking_report(cursor)

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()