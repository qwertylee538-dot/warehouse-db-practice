"""
CLI: a single interactive menu that ties the whole project together.

WHY THIS FILE EXISTS:
Every step so far (step1 through step10) is its own standalone script
you run separately from the terminal. That's great for LEARNING each
concept in isolation, but it's not how a real user would experience
the finished project — nobody wants to remember ten file names. This
file wraps the reporting functions from step4, step8, and step10 into
one menu-driven program: run `python cli.py` once, then pick options
by number, in a loop, until you choose to quit.

WHAT'S NEW HERE (vs earlier steps):
  - A `while True:` loop that keeps showing the menu until the user quits.
  - `input()` to read what the user typed, and turning that text into
    a decision (an if/elif chain).
  - Wrapping every option in try/except so a typo or bad input doesn't
    crash the whole program — it just prints an error and shows the
    menu again.
  - Reusing functions we ALREADY wrote and tested in earlier files,
    rather than rewriting the SQL — cli.py imports them instead.
"""

from step1_connect import get_connection
from step4_queries import current_stock_report, low_stock_report, movements_by_category
from step8_store_functions import compare_stores, low_stock_by_store, top_products_by_store
from step10_prices import inventory_value_by_store, most_valuable_products

MENU = """
============================================
 WAREHOUSE INVENTORY SYSTEM
============================================
 1. Current stock per product (whole company)
 2. Low stock alert (whole company)
 3. Movement volume by category
 4. Compare stores
 5. Low stock per store
 6. Top products per store
 7. Inventory value per store
 8. Most valuable products
 0. Quit
============================================
"""


def main() -> None:
    connection = get_connection()

    while True:
        print(MENU)
        choice = input("Choose an option: ").strip()

        if choice == "0":
            print("Goodbye!")
            break

        cursor = connection.cursor()
        try:
            if choice == "1":
                current_stock_report(cursor)
            elif choice == "2":
                threshold = input("Threshold (default 100): ").strip()
                threshold = int(threshold) if threshold else 100
                low_stock_report(cursor, threshold=threshold)
            elif choice == "3":
                movements_by_category(cursor)
            elif choice == "4":
                compare_stores(cursor)
            elif choice == "5":
                threshold = input("Threshold (default 50): ").strip()
                threshold = int(threshold) if threshold else 50
                low_stock_by_store(cursor, threshold=threshold)
            elif choice == "6":
                top_n = input("How many per store (default 2): ").strip()
                top_n = int(top_n) if top_n else 2
                top_products_by_store(cursor, top_n=top_n)
            elif choice == "7":
                inventory_value_by_store(cursor)
            elif choice == "8":
                top_n = input("How many products (default 3): ").strip()
                top_n = int(top_n) if top_n else 3
                most_valuable_products(cursor, top_n=top_n)
            else:
                print("Unknown option, try again.")
        except Exception as error:
            print(f"Something went wrong: {error}")
            connection.rollback()
        finally:
            cursor.close()

        input("\nPress Enter to continue...")

    connection.close()


if __name__ == "__main__":
    main()