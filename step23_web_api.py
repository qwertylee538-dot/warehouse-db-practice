"""
STEP 23: A secured web API — logins, passwords, and access tokens.

WHAT'S GENUINELY NEW HERE:
  1. PASSWORD HASHING: We never store a password itself — only a
     one-way HASH of it (via passlib's bcrypt). If our database were
     ever stolen, the attacker gets hashes, not actual passwords.
  2. LOGIN -> TOKEN: A user posts their username+password ONCE to
     /login. If correct, they get back a signed JWT — a piece of text
     the server can verify came from itself without hitting the
     database again for every request.
  3. PROTECTED ENDPOINTS: Every business endpoint requires a valid
     token. No token, no access.

WHAT THIS FILE DELIBERATELY DOES NOT DO:
It does not implement real payment processing, a certified fiscal
cash register (54-ФЗ), or a real government EGAIS/Mercury connection
— those require external certified providers and legal registration,
not code alone.
"""

import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel

from step1_connect import get_connection

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-secret-change-this-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

app = FastAPI(title="Warehouse API (secured)")


def ensure_users_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            employee_id INTEGER NOT NULL REFERENCES employees(id),
            username VARCHAR(50) NOT NULL UNIQUE,
            password_hash VARCHAR(200) NOT NULL
        );
        """
    )


def create_user(cursor, employee_id: int, username: str, plain_password: str) -> None:
    password_hash = pwd_context.hash(plain_password)
    cursor.execute(
        "INSERT INTO users (employee_id, username, password_hash) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING;",
        (employee_id, username, password_hash),
    )


def authenticate_user(cursor, username: str, plain_password: str):
    cursor.execute(
        "SELECT id, employee_id, password_hash FROM users WHERE username = %s;",
        (username,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    user_id, employee_id, password_hash = row
    if not pwd_context.verify(plain_password, password_hash):
        return None
    return {"user_id": user_id, "employee_id": employee_id, "username": username}


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        return {"username": username, "employee_id": payload.get("employee_id")}
    except jwt.PyJWTError:
        raise credentials_exception


@app.on_event("startup")
def startup() -> None:
    connection = get_connection()
    cursor = connection.cursor()
    ensure_users_table(cursor)
    connection.commit()

    cursor.execute("SELECT id FROM employees WHERE full_name = 'Иванова Анна';")
    row = cursor.fetchone()
    if row is not None:
        create_user(cursor, employee_id=row[0], username="anna", plain_password="demo-password-123")
        connection.commit()

    cursor.close()
    connection.close()


@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    connection = get_connection()
    cursor = connection.cursor()
    user = authenticate_user(cursor, form_data.username, form_data.password)
    cursor.close()
    connection.close()

    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    token = create_access_token({"sub": user["username"], "employee_id": user["employee_id"]})
    return {"access_token": token, "token_type": "bearer"}


class ShipRequest(BaseModel):
    product_id: int
    store_id: int
    quantity: float
    note: str


@app.get("/me")
def read_current_user(user: dict = Depends(get_current_user)):
    return user


@app.get("/stock/{product_id}/{store_id}")
def get_stock(product_id: int, store_id: int, user: dict = Depends(get_current_user)):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN movement_type = 'IN' THEN quantity ELSE -quantity END), 0)
        FROM stock_movements WHERE product_id = %s AND store_id = %s;
        """,
        (product_id, store_id),
    )
    stock = cursor.fetchone()[0]
    cursor.close()
    connection.close()
    return {"product_id": product_id, "store_id": store_id, "current_stock": stock}


@app.post("/ship")
def ship(request: ShipRequest, user: dict = Depends(get_current_user)):
    from step14_employees import ship_stock_as_employee

    connection = get_connection()
    success = ship_stock_as_employee(
        connection,
        product_id=request.product_id,
        store_id=request.store_id,
        quantity=request.quantity,
        note=request.note,
        employee_id=user["employee_id"],
    )
    connection.close()

    if not success:
        raise HTTPException(status_code=400, detail="Shipment rejected — check available stock")
    return {"status": "shipped", "by_employee_id": user["employee_id"]}


@app.get("/")
def root():
    return {
        "message": "Warehouse API. POST /login with username=anna&password=demo-password-123 to get a token, "
        "then use it as 'Authorization: Bearer <token>' on other endpoints. See /docs."
    }