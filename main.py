import json
import stripe
import redis.asyncio as redis
from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.middleware import Middleware
from starlette.responses import RedirectResponse
import logging
from typing import Optional
import aiofiles

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration (replace with actual keys)
STRIPE_API_KEY = "sk_test_51Pn9MbDo5uWbWPXU81NQmpueBJo8XjS9NCxpxt6Z2rVNPysIZ2mR7dUZgYZvdVwq5mHOkauc89LOdfvw1zf2n2Xu00eerSOuqR"
STRIPE_ENDPOINT_SECRET = "whsec_c5lc8jr7ijEbaMgegU5wVpt1BuQ53mKz"
STRIPE_PAYMENT_LINK = "https://buy.stripe.com/test_aEUeYSdZEaR9b7O288"
REDIS_URL = "redis://default:m3S2jrjbheJx1HUHuqkhQ8QGWyQpJTB0@redis-15159.c243.eu-west-1-3.ec2.redns.redis-cloud.com:15159"

stripe.api_key = STRIPE_API_KEY

# Initialize FastAPI
middleware = [
    Middleware(BaseHTTPMiddleware, dispatch=lambda request, call_next: call_next(request))
]
app = FastAPI(
    title="Crypto Advisor Payment API",
    description="API to manage subscription payments for the Crypto Advisor platform.",
    version="1.0.0",
    middleware=middleware
)

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
@app.get("/getPaymentURL", summary="Generate Payment URL")
async def get_payment_url(user_id: str = Depends(get_user_id)):
    """
    Generate and return a payment URL with a client_reference_id.
    """
    url = f"{STRIPE_PAYMENT_LINK}?client_reference_id={user_id}"
    logger.info(f"Generated payment URL for {user_id}: {url}")
    return {"message": "Complete payment using the link below.", "url": url}

@app.post("/webhook/stripe", summary="Handle Stripe Webhook")
async def webhook_received(
    request: Request, stripe_signature: str = Header(..., alias="Stripe-Signature")
):
    """
    Handle Stripe webhook events.
    """
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=stripe_signature, secret=STRIPE_ENDPOINT_SECRET
        )
        logger.info(f"Stripe webhook event received: {event['type']}")

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            user_id = session.get("client_reference_id")
            if user_id:
                await store_payment_status(user_id, "paid")
                logger.info(f"Payment status for {user_id} updated to 'paid'")

        return JSONResponse(content={"status": "success"}, status_code=200)

    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid Stripe signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=400, detail="Webhook processing error")

@app.get("/hasUserPaid", summary="Check Payment Status")
async def has_user_paid(user_id: str = Depends(get_user_id)):
    """
    Check if the user has paid based on user_id.
    """
    status = await retrieve_payment_status(user_id)
    if status == "paid":
        return {"paid": True}
    return {"paid": False}

@app.get("/privacy", response_class=HTMLResponse, summary="Privacy Policy")
async def privacy():
    """
    Serve the privacy policy HTML content.
    """
    try:
        async with aiofiles.open("./api/privacy_policy.html", "r") as file:
            content = await file.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        logger.error("Privacy policy file not found")
        raise HTTPException(status_code=404, detail="Privacy policy file not found")

@app.get("/", summary="Root Redirect")
async def root():
    """
    Redirect to OpenAPI docs by default.
    """
    return RedirectResponse(url="/docs")
