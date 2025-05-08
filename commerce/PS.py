from fastapi import Body
from pydantic import BaseModel
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

class TransferMoneyRequest(BaseModel):
    receiver_id: int
    amount: int

@app.post("/e-wallet/transfer")
def transfer_money(body: TransferMoneyRequest, request: Request):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Transfer amount must be positive")

    conn = get_db()
    cur = conn.cursor()
    try:
        conn.autocommit = False

        cur.execute(
            "UPDATE ACCOUNT SET balance = balance - %s WHERE account_id = %s AND balance >= %s RETURNING balance",
            (body.amount, request.state.account_id, body.amount)
        )
        sender_balance = cur.fetchone()
        if not sender_balance:
            raise HTTPException(status_code=400, detail="Insufficient funds or sender not found")

        cur.execute(
            "UPDATE ACCOUNT SET balance = balance + %s WHERE account_id = %s RETURNING balance",
            (body.amount, body.receiver_id)
        )
        receiver_balance = cur.fetchone()
        if not receiver_balance:
            raise HTTPException(status_code=404, detail="Receiver account not found")

        current_timestamp = datetime.now()
        cur.execute(
            "INSERT INTO MONEY_TRANSACTION (amount, timestamp, account_id) VALUES (%s, %s, %s)",
            (-body.amount, current_timestamp, request.state.account_id)  
        )
        cur.execute(
            "INSERT INTO MONEY_TRANSACTION (amount, timestamp, account_id) VALUES (%s, %s, %s)",
            (body.amount, current_timestamp, body.receiver_id)  
        )

        conn.commit()
        return {
            "message": "Transfer successful",
            "sender_new_balance": sender_balance[0],
            "receiver_id": body.receiver_id
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
