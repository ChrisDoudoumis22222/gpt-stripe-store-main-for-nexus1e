#!/usr/bin/env python3.11
# Python 3.11 or newer required.

import json
import stripe
import redis.asyncio as redis
from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
import logging
import uvicorn
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
STRIPE_API_KEY = "sk_test_51Pn9MbDo5uWbWPXU81NQmpueBJo8XjS9NCxpxt6Z2rVNPysIZ2mR7dUZgYZvdVwq5mHOkauc89LOdfvw1zf2n2Xu00eerSOuqR"
STRIPE_ENDPOINT_SECRET = "whsec_c5lc8jr7ijEbaMgegU5wVpt1BuQ53mKz"
STRIPE_PAYMENT_LINK = "https://buy.stripe.com/test_aEUeYSdZEaR9b7O288"
REDIS_URL = "redis://localhost:6379"

stripe.api_key = STRIPE_API_KEY

# Initialize FastAPI
app = FastAPI(title="Crypto Advisor Payment API")

# Middleware to preserve raw request body
class RawBodyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        request.state.body = await request.body()
        return await call_next(request)

app.add_middleware(RawBodyMiddleware)

# Redis connection
redis_client: Optional[redis.Redis] = None

async def get_redis_connection() -> redis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        logger.info("Connected to Redis")
    return redis_client

# Helper functions for payment status
async def store_payment_status(user_id: str, status: str):
    redis_conn = await get_redis_connection()
    await redis_conn.set(user_id, status)
    logger.info(f"Stored payment status for {user_id}: {status}")

async def retrieve_payment_status(user_id: str) -> Optional[str]:
    redis_conn = await get_redis_connection()
    status = await redis_conn.get(user_id)
    logger.info(f"Retrieved payment status for {user_id}: {status}")
    return status

# Dependency to extract user_id from headers
async def get_user_id(user_id: Optional[str] = Header(None)) -> str:
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user_id header")
    return user_id

# Routes
@app.get("/payment-link", summary="Generate Payment Link")
async def payment_link(user_id: str = Depends(get_user_id)):
    url = f"{STRIPE_PAYMENT_LINK}?client_reference_id={user_id}"
    logger.info(f"Generated payment link for {user_id}: {url}")
    return {"message": "Complete payment using the link below.", "url": url}

@app.get("/check-payment", summary="Check Payment Status")
async def check_payment(user_id: str = Depends(get_user_id)):
    status = await retrieve_payment_status(user_id)
    if status == "paid":
        return {"paid": True}
    return {"paid": False}

@app.post("/webhook/stripe", summary="Handle Stripe Webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(...)):
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_ENDPOINT_SECRET)
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            user_id = session.get("client_reference_id")
            if user_id:
                await store_payment_status(user_id, "paid")
        return JSONResponse(content={"status": "success"}, status_code=200)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=400, detail="Webhook error")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
