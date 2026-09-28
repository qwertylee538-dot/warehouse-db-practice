"""
One-off correction: the bug in already_returned_quantity() let a
second, invalid return through (reason='test', linked to order #1).
This deletes that specific erroneous movement so the data reflects
only the one legitimate return.
"""

from step1_connect import get_connection


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        DELETE FROM stock_movements
        WHERE movement_type = 'RETURN' AND reason = 'test'
        RETURNING id;
        """
    )
    deleted = cursor.fetchall()
    connection.commit()

    if deleted:
        print(f"Deleted {len(deleted)} erroneous return movement(s): ids {[row[0] for row in deleted]}")
    else:
        print("Nothing to delete.")

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()