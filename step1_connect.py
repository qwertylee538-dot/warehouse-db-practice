"""
STEP 1: Connect to the PostgreSQL database from Python.

WHY START HERE:
Before we can create tables or store any data, we need to prove
Python can actually talk to PostgreSQL at all. This script does
nothing except open a connection, ask the database "what version are
you running?", print the answer, and close the connection cleanly.
If this works, everything else in this series can build on top of it.

WHY psycopg2:
`psycopg2` is the most widely used PostgreSQL driver for Python — the
library that knows how to speak PostgreSQL's network protocol. Later,
bigger projects often use an ORM (Object-Relational Mapper) like
SQLAlchemy on top of it, but starting with the raw driver first means
we actually see the real SQL we're sending and the real rows we get
back, instead of that being hidden behind another layer of magic.

WHY THE CONNECTION DETAILS LIVE IN .env:
Same reasoning as the DEEPSEEK_API_KEY in the AI agent projects — a
database password is a secret. It must never be hardcoded into a
Python file that could end up on GitHub. Instead we read it from
environment variables (loaded from .env by python-dotenv), so the
.env file — which IS in .gitignore — is the only place the real
password lives.
"""

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Read every connection detail from environment variables instead of
# hardcoding them — this is what lets the exact same code work on a
# different computer with different DB credentials, without editing
# the code itself.
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not all([DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD]):
    raise RuntimeError("One or more DB_* variables are missing — check your .env file.")


def get_connection():
    """Open and return a new connection to the database. Every script
    in this series will reuse this exact same function, so the
    connection details only need to be correct in ONE place.
    """
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


if __name__ == "__main__":
    print(f"Connecting to database '{DB_NAME}' on {DB_HOST}:{DB_PORT}...")

    # A "connection" is the link to the database server itself. A
    # "cursor" is what you actually use to run SQL commands and read
    # back results through that connection — think of the connection
    # as the phone line, and the cursor as you actually speaking.
    connection = get_connection()
    cursor = connection.cursor()

    # A raw SQL command, sent exactly as PostgreSQL understands it.
    # This is the same SQL you'd type directly into pgAdmin's Query Tool.
    cursor.execute("SELECT version();")

    # fetchone() reads back a single row of the result — here, just
    # one row with one column: the version string.
    result = cursor.fetchone()
    print("Connected successfully!")
    print(f"PostgreSQL version: {result[0]}")

    # Always close what you opened — leaving connections open is a
    # common source of "too many connections" errors in real apps.
    cursor.close()
    connection.close()
    print("Connection closed.")