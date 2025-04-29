import json
import os
from http.client import responses

from dotenv import load_dotenv

load_dotenv()

import httpx


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