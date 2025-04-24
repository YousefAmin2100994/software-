# main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncpg
import os

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL", "")


@app.on_event("startup")
async def startup():
    app.state.db = await asyncpg.create_pool(DATABASE_URL)


@app.on_event("shutdown")
async def shutdown():
    await app.state.db.close()


class AddMoneyRequest(BaseModel):
    account_id: int
    amount: int
    timestamp: int


@app.get("/e-wallet")
async def get_wallet_details(account_id: int):
    async with app.state.db.acquire() as conn:
        result = await conn.fetchrow("""
            SELECT account_id, balance FROM ACCOUNT WHERE account_id = $1
        """, account_id)
        if not result:
            raise HTTPException(status_code=404, detail="Account not found")
    return dict(result)


@app.post("/e-wallet")
async def add_money_to_wallet(request: AddMoneyRequest):
    async with app.state.db.acquire() as conn:
        async with conn.transaction():
            # Update balance
            await conn.execute("""
                UPDATE ACCOUNT SET balance = balance + $1 WHERE account_id = $2
            """, request.amount, request.account_id)

            # Insert transaction
            await conn.execute("""
                INSERT INTO MONEY_TRANSACTION (amount, timestamp, account_id)
                VALUES ($1, $2, $3)
            """, request.amount, request.timestamp, request.account_id)
    return {"message": "Money added to wallet"}


@app.get("/e-wallet/transactions")
async def get_transaction_history(account_id: int):
    async with app.state.db.acquire() as conn:
        records = await conn.fetch("""
            SELECT amount, timestamp FROM MONEY_TRANSACTION
            WHERE account_id = $1 ORDER BY timestamp DESC
        """, account_id)
    return [dict(record) for record in records]
