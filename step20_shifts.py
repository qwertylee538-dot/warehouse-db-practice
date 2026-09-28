"""
STEP 20: Shifts — открыть/закрыть смену, and a report of everything
that happened during one.

WHY THIS IS DIFFERENT FROM employee_activity_report (step14):
step14 answers "how much has this employee EVER done, all-time."
A shift report answers a more specific, time-boxed question a real
warehouse manager asks constantly: "what happened during THIS
specific work session, today, by this person?"

HOW THIS IS MODELED:
  - shifts: one row per work session — which employee, which store,
    when it opened, and when it closed (closed_at starts NULL,
    meaning "still open").
  - Every stock_movements row already has a created_at timestamp —
    a shift report is: "every movement by this employee, at this
    store, where created_at falls between opened_at and closed_at."

WHY YOU CAN'T OPEN TWO SHIFTS FOR THE SAME EMPLOYEE AT ONCE:
Physically, a person can't be clocked into two shifts simultaneously —
if the system allowed it, movements could get attributed to the wrong
shift, or a shift could never properly close.
"""

from step1_connect import get_connection


def ensure_shifts_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS shifts (
            id SERIAL PRIMARY KEY,
            employee_id INTEGER NOT NULL REFERENCES employees(id),
            store_id INTEGER NOT NULL REFERENCES stores(id),
            opened_at TIMESTAMP NOT NULL DEFAULT NOW(),
            closed_at TIMESTAMP
        );
        """
    )


def open_shift(cursor, employee_id: int, store_id: int):
    cursor.execute(
        "SELECT id FROM shifts WHERE employee_id = %s AND closed_at IS NULL;",
        (employee_id,),
    )
    existing = cursor.fetchone()
    if existing is not None:
        print(f"  REJECTED: employee {employee_id} already has an open shift (#{existing[0]}).")
        return None

    cursor.execute(
        "INSERT INTO shifts (employee_id, store_id) VALUES (%s, %s) RETURNING id;",
        (employee_id, store_id),
    )
    shift_id = cursor.fetchone()[0]
    print(f"  OK: shift #{shift_id} opened.")
    return shift_id


def close_shift(cursor, shift_id: int) -> bool:
    cursor.execute("SELECT closed_at FROM shifts WHERE id = %s;", (shift_id,))
    row = cursor.fetchone()
    if row is None:
        print(f"  REJECTED: no shift with id={shift_id}.")
        return False
    if row[0] is not None:
        print(f"  REJECTED: shift #{shift_id} is already closed.")
        return False

    cursor.execute("UPDATE shifts SET closed_at = NOW() WHERE id = %s;", (shift_id,))
    print(f"  OK: shift #{shift_id} closed.")
    return True


def shift_report(cursor, shift_id: int) -> None:
    cursor.execute(
        """
        SELECT e.full_name, s.store_id, s.opened_at, s.closed_at
        FROM shifts s
        JOIN employees e ON e.id = s.employee_id
        WHERE s.id = %s;
        """,
        (shift_id,),
    )
    full_name, store_id, opened_at, closed_at = cursor.fetchone()
    print(f"\n=== Shift #{shift_id} report: {full_name}, store {store_id} ===")
    print(f"  Opened: {opened_at}")
    print(f"  Closed: {closed_at if closed_at else '(still open)'}")

    cursor.execute(
        """
        SELECT movement_type, COUNT(*), COALESCE(SUM(quantity), 0)
        FROM stock_movements
        WHERE employee_id = (SELECT employee_id FROM shifts WHERE id = %s)
          AND store_id = %s
          AND created_at >= %s
          AND created_at <= COALESCE(%s, NOW())
        GROUP BY movement_type
        ORDER BY movement_type;
        """,
        (shift_id, store_id, opened_at, closed_at),
    )
    rows = cursor.fetchall()
    if not rows:
        print("  No movements recorded during this shift.")
        return
    headers = ["Movement type", "Count", "Total quantity"]
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, value in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(value)))
    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print("  " + header_line)
    print("  " + "-" * len(header_line))
    for row in rows:
        print("  " + "  ".join(str(value).ljust(col_widths[i]) for i, value in enumerate(row)))


def main() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    print("Ensuring shifts table exists...")
    ensure_shifts_table(cursor)
    connection.commit()

    cursor.execute("SELECT id FROM employees WHERE full_name = 'Иванова Анна';")
    anna_id = cursor.fetchone()[0]

    print("\nOpening a shift for Anna at store 1...")
    shift_id = open_shift(cursor, employee_id=anna_id, store_id=1)
    connection.commit()

    print("\nTrying to open a SECOND shift for Anna while the first is still open (should be rejected)...")
    open_shift(cursor, employee_id=anna_id, store_id=1)
    connection.commit()

    if shift_id is not None:
        print("\nRecording a movement during the shift...")
        cursor.execute(
            """
            INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, note, employee_id)
            VALUES (5, 1, 'OUT', 2, 'Order pickup during shift', %s);
            """,
            (anna_id,),
        )
        connection.commit()

        print("\nClosing the shift...")
        close_shift(cursor, shift_id)
        connection.commit()

        shift_report(cursor, shift_id)

    cursor.close()
    connection.close()


if __name__ == "__main__":
    main()