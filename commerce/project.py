from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List
from datetime import datetime
import psycopg2
import os
from http.client import responses

from dotenv import load_dotenv

load_dotenv()

import httpx

app = FastAPI()

def create_session(amount_cents):
    url = "https://accept.paymob.com/v1/intention/"

    integration_id = os.environ.get('PAYMOB_INTEGRATION_ID')

    payload = {
        "amount": amount_cents,
        "currency": "EGP",
        "payment_methods": [integration_id],
        "items": [
            {
                "name": "Wallet Charge",
                "amount": amount_cents,
                "description": "Charge your wallet",
                "quantity": 1
            }
        ],
        "billing_data": {
            "apartment": "6",
            "first_name": "Ammar",
            "last_name": "Sadek",
            "street": "938, Al-Jadeed Bldg",
            "building": "939",
            "phone_number": "+96824480228",
            "country": "OMN",
            "email": "AmmarSadek@gmail.com",
            "floor": "1",
            "state": "Alkhuwair"
        },
        "customer": {
            "first_name": "Ammar",
            "last_name": "Sadek",
            "email": "AmmarSadek@gmail.com",
            "extras": {
                "re": "22"
            }
        },
        "extras": {
            "ee": 22
        }
    }

    headers = {
        'Authorization': 'Token ' + os.environ.get('PAYMOB_API_SECRET_KEY'),
        'Content-Type': 'application/json'
    }


    try:
        response = httpx.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        if response.status_code == 201:
            return f"https://accept.paymob.com/unifiedcheckout/?publicKey={os.environ.get('PAYMOB_API_PUBLIC_KEY')}&clientSecret={data.get("client_secret")}"
        else:
            raise Exception("Failed to create session: " + str(data))
    except httpx.HTTPStatusError as e:
        raise Exception(f"HTTP error: {e.response.status_code} - {responses.get(e.response.status_code)}")
    except httpx.RequestError as e:
        raise Exception(f"Request error: {e}")

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
            return {"balance": result[1]}
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
        return {"session_id": create_session(body.amount)}
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
        return [{"amount": t[0], "timestamp": int(t[1].timestamp())} for t in transactions]
    finally:
        cur.close()
        conn.close()
