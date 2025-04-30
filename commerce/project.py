import os

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List
from datetime import datetime
import psycopg2

app = FastAPI()

# Database connection
def get_db():
    conn = psycopg2.connect(
        dbname=os.environ.get('POSTGRES_DATABASE'),
        user=os.environ.get('POSTGRES_USER'),
        password=os.environ.get('POSTGRES_PASSWORD'),
        host=os.environ.get('POSTGRES_HOST'),
        port=os.environ.get('POSTGRES_PORT')
    )
    return conn

# Middleware to validate JWT and extract account_id
async def auth_middleware(request: Request, call_next):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid or missing Authorization header"}
        )

    token = auth_header.split(" ")[1]

    # Call auth microservice to validate token and get account_id
    async with httpx.AsyncClient() as client:
        try:
            # noinspection HttpUrlsUsage
            response = await client.post(
                "http://" + os.environ.get('AUTH_HOST')  + ":" + os.environ.get('AUTH_PORT') + "/auth/verify-token",
                json={"token": token},
                timeout=5.0
            )
            response.raise_for_status()
            auth_data = response.json()
            account_id = auth_data.get("user")
            if not account_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: account_id not found"
                )
            # Attach account_id to request state
            request.state.account_id = account_id
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token validation failed"
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Auth service unavailable"
            )

    response = await call_next(request)
    return response

# Register middleware
app.middleware("http")(auth_middleware)

# models
class AddMoneyRequest(BaseModel):
    amount: int

class WalletDetailsResponse(BaseModel):
    balance: int

class TransactionResponse(BaseModel):
    amount: int
    timestamp: int

# wallet details
@app.get("/e-wallet", response_model=WalletDetailsResponse)
def get_wallet_details(request: Request):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT account_id, balance FROM ACCOUNT WHERE account_id = %s", (request.state.account_id,))
        result = cur.fetchone()
        if result:
            return {"account_id": result[0], "balance": result[1]}
        else:
            raise HTTPException(status_code=404, detail="Account not found")
    finally:
        cur.close()
        conn.close()

# Add money to wallet
@app.post("/e-wallet")
def add_money_to_wallet(body: AddMoneyRequest, request: Request):
    conn = get_db()
    cur = conn.cursor()
    try:
        # Update balance
        cur.execute(
            "UPDATE ACCOUNT SET balance = balance + %s WHERE account_id = %s RETURNING balance",
            (body.amount, request.state.account_id)
        )
        updated_balance = cur.fetchone()
        if not updated_balance:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # Insert into MONEY_TRANSACTION
        current_timestamp = datetime.now()
        cur.execute(
            "INSERT INTO MONEY_TRANSACTION (amount, timestamp, account_id) VALUES (%s, %s, %s)",
            (body.amount, current_timestamp, request.state.account_id)
        )

        conn.commit()
        return {"message": "Money added successfully", "new_balance": updated_balance[0]}
    finally:
        cur.close()
        conn.close()

# Get transaction history
@app.get("/e-wallet/transactions", response_model=List[TransactionResponse])
def get_transaction_history(request: Request):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT amount, timestamp FROM MONEY_TRANSACTION WHERE account_id = %s ORDER BY timestamp DESC",
            (request.state.account_id,)
        )
        transactions = cur.fetchall()
        return [{"amount": t[0], "timestamp": t[1]} for t in transactions]
    finally:
        cur.close()
        conn.close()
