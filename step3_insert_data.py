"""
STEP 3: Insert sample data — categories, products, and stock movements.

THE #1 RULE OF SQL: NEVER BUILD QUERIES WITH STRING FORMATTING.
It is tempting to write:
    cursor.execute(f"INSERT INTO categories (name) VALUES ('{name}')")
DO NOT DO THIS. If `name` ever comes from outside your own code (a
website form, an API request, anything a user types), someone could
send a category name like:  '); DROP TABLE categories; --
and that string, pasted directly into the SQL text, would run as a
SECOND command — deleting the whole table. This is called "SQL
injection" and it's one of the most common real-world security bugs.

THE FIX — PARAMETERIZED QUERIES:
    cursor.execute("INSERT INTO categories (name) VALUES (%s)", (name,))
Here `%s` is a placeholder, and the actual value is passed SEPARATELY
as a tuple. psycopg2 sends the query and the value to PostgreSQL as
two distinct pieces — the database engine treats the value purely as
DATA, never as part of the command, no matter what characters it
contains. This is not just "safer", it's the only correct way to
insert values from Python — always use %s placeholders, never string
formatting, for any value in a SQL query.

WHY "RETURNING id":
When we insert a category, we need its auto-generated id afterward,
so we can use it as the category_id when inserting a product. Adding
"RETURNING id" to an INSERT statement makes PostgreSQL hand that new
id straight back to us in the same round trip, instead of running a
separate SELECT to look it up.
"""

from step1_connect import get_connection

CATEGORIES = [
    "Стройматериалы",
    "Крепёж",
    "Инструменты",
    "Электрика",
]

# Each product: (sku, name, unit, category_name)
PRODUCTS = [
    ("SKU-001", "Цемент М500, мешок 50 кг", "pcs", "Стройматериалы"),
    ("SKU-002", "Кирпич керамический рядовой", "pcs", "Стройматериалы"),
    ("SKU-003", "Саморезы по дереву 3x25 мм", "pcs", "Крепёж"),
    ("SKU-004", "Дюбель-гвоздь 6x40 мм", "pcs", "Крепёж"),
    ("SKU-005", "Перфоратор Bosch GBH 2-26", "pcs", "Инструменты"),
    ("SKU-006", "Кабель ВВГ 3x2.5", "m", "Электрика"),
]

# Each movement: (sku, movement_type, quantity, note)
MOVEMENTS = [
    ("SKU-001", "IN", 200, "Поступление от поставщика №1"),
    ("SKU-001", "OUT", 40, "Отгрузка заказ №1042"),
    ("SKU-002", "IN", 5000, "Поступление от поставщика №2"),
    ("SKU-002", "OUT", 1200, "Отгрузка заказ №1043"),
    ("SKU-003", "IN", 10000, "Поступление от поставщика №1"),
    ("SKU-003", "OUT", 2500, "Отгрузка заказ №1044"),
    ("SKU-004", "IN", 8000, "Поступление от поставщика №1"),
    ("SKU-005", "IN", 15, "Поступление от поставщика №3"),
    ("SKU-005", "OUT", 3, "Отгрузка заказ №1045"),
    ("SKU-006", "IN", 500, "Поступление от поставщика №3"),
    ("SKU-006", "OUT", 120, "Отгрузка заказ №1046"),
]


def insert_categories(cursor) -> dict:
    """Insert every category and return a dict mapping name -> id, so
    products can look up the right category_id below.
    """
    name_to_id = {}
    for name in CATEGORIES:
        cursor.execute(
            "INSERT INTO categories (name) VALUES (%s) RETURNING id;",
            (name,),
        )
        new_id = cursor.fetchone()[0]
        name_to_id[name] = new_id
        print(f"  Inserted category '{name}' (id={new_id})")
    return name_to_id


def insert_products(cursor, category_ids: dict) -> dict:
    """Insert every product and return a dict mapping sku -> id, so
    stock movements can look up the right product_id below.
    """
    sku_to_id = {}
    for sku, name, unit, category_name in PRODUCTS:
        category_id = category_ids[category_name]
        cursor.execute(
            """
            INSERT INTO products (sku, name, unit, category_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
            """,
            (sku, name, unit, category_id),
        )
        new_id = cursor.fetchone()[0]
        sku_to_id[sku] = new_id
        print(f"  Inserted product '{name}' (sku={sku}, id={new_id})")
    return sku_to_id


def insert_movements(cursor, product_ids: dict) -> None:
    for sku, movement_type, quantity, note in MOVEMENTS:
        product_id = product_ids[sku]
        cursor.execute(
            """
            INSERT INTO stock_movements (product_id, movement_type, quantity, note)
            VALUES (%s, %s, %s, %s);
            """,
            (product_id, movement_type, quantity, note),
        )
        print(f"  {movement_type} {quantity} of {sku} — {note}")


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    print("Inserting categories...")
    category_ids = insert_categories(cursor)

    print("\nInserting products...")
    product_ids = insert_products(cursor, category_ids)

    print("\nInserting stock movements...")
    insert_movements(cursor, product_ids)

    connection.commit()
    print("\nDone. All sample data committed.")

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()