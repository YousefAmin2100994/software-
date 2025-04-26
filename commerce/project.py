import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import datetime
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

# models
class AddMoneyRequest(BaseModel):
    account_id: int
    amount: int

class WalletDetailsResponse(BaseModel):
    account_id: int
    balance: int

class TransactionResponse(BaseModel):
    amount: int
    timestamp: int

# wallet details
@app.get("/e-wallet", response_model=WalletDetailsResponse)
def get_wallet_details(account_id: int):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT account_id, balance FROM ACCOUNT WHERE account_id = %s", (account_id,))
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
def add_money_to_wallet(request: AddMoneyRequest):
    conn = get_db()
    cur = conn.cursor()
    try:
        # Update balance
        cur.execute(
            "UPDATE ACCOUNT SET balance = balance + %s WHERE account_id = %s RETURNING balance",
            (request.amount, request.account_id)
        )
        updated_balance = cur.fetchone()
        if not updated_balance:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # Insert into MONEY_TRANSACTION
        current_timestamp = int(datetime.datetime.utcnow().timestamp())
        cur.execute(
            "INSERT INTO MONEY_TRANSACTION (amount, timestamp, account_id) VALUES (%s, %s, %s)",
            (request.amount, current_timestamp, request.account_id)
        )

        conn.commit()
        return {"message": "Money added successfully", "new_balance": updated_balance[0]}
    finally:
        cur.close()
        conn.close()

# Get transaction history
@app.get("/e-wallet/transactions", response_model=List[TransactionResponse])
def get_transaction_history(account_id: int):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT amount, timestamp FROM MONEY_TRANSACTION WHERE account_id = %s ORDER BY timestamp DESC",
            (account_id,)
        )
        transactions = cur.fetchall()
        return [{"amount": t[0], "timestamp": t[1]} for t in transactions]
    finally:
        cur.close()
        conn.close()
