#!/usr/bin/env python3.6
# Python 3.6 or newer required.

import os
import json
import stripe
import aioredis
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from fastapi.openapi.utils import get_openapi

# Load environment variables
load_dotenv()

# Stripe and app setup
stripe.api_key = os.getenv("STRIPE_API_KEY", "sk_test_51Pn9MbDo5uWbWPXU81NQmpueBJo8XjS9NCxpxt6Z2rVNPysIZ2mR7dUZgYZvdVwq5mHOkauc89LOdfvw1zf2n2Xu00eerSOuqR")
endpoint_secret = os.getenv("STRIPE_ENDPOINT_SECRET", "whsec_c5lc8jr7ijEbaMgegU5wVpt1BuQ53mKz")
product_id = os.getenv("STRIPE_PRODUCT_ID", "we_1QfSOPDo5uWbWPXUoR9sz0kD")
payment_link = os.getenv("STRIPE_PAYMENT_LINK", "https://buy.stripe.com/test_aEUeYSdZEaR9b7O288")
redis_url = os.getenv("REDIS_URL", "redis://default:mS32jrbheJx1HUHuqkhQ8QGWyQpJTB0@redis-15159.c243.eu-west-1-3.ec2.redns.redis-cloud.com:15159")
app_url = os.getenv("APP_URL", "https://gpt-stripe-store-main-for-nexus1e.vercel.app/")
app_name = os.getenv("APP_NAME", "Nexus Wire")

# Initialize FastAPI app
app = FastAPI(
    servers=[
        {
            "url": app_url,
            "description": "Production environment",
        },
    ],
    title="Nexus Wire API",
    version="1.0.0",
    description="API for managing Stripe payments and Redis-based payment status tracking.",
)

# Middleware to preserve raw request body
class RawBodyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        request.state.body = await request.body()
        return await call_next(request)

app.add_middleware(RawBodyMiddleware)

# Initialize Redis connection
redis = None

async def get_redis_connection():
    global redis
    if redis is None:
        redis = await aioredis.from_url(redis_url, decode_responses=True)
    return redis

# Helper functions for storing and retrieving payment statuses
async def store_payment_status(conversation_id: str, status: str):
    """
    Store payment status in Redis.
    """
    redis_conn = await get_redis_connection()
    await redis_conn.set(conversation_id, status)

async def retrieve_paid_status(conversation_id: str):
    """
    Retrieve payment status from Redis.
    """
    redis_conn = await get_redis_connection()
    return await redis_conn.get(conversation_id)

# Custom OpenAPI Schema
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return openapi_schema

app.openapi = custom_openapi

# Routes
@app.get("/getPaymentURL")
async def get_payment_url(openai_conversation_id: str = Header(None)):
    """
    Generate and return a payment URL with a client_reference_id.
    """
    if not openai_conversation_id:
        raise HTTPException(
            status_code=400, detail="Missing openai-conversation-id header"
        )

    # Generate the payment link
    url = f"{payment_link}?client_reference_id={openai_conversation_id}"
    return {"message": "Tell the user to click here and type 'continue' when they're done.", "url": url}

@app.post("/webhook/stripe")
async def webhook_received(request: Request, stripe_signature: str = Header(None, alias="Stripe-Signature")):
    """
    Handle Stripe webhook events.
    """
    try:
        payload = await request.body()  # Use raw body for Stripe validation
        payload_str = payload.decode("utf-8")
        print("Headers:", request.headers)
        print("Payload:", payload_str)  # Debug payload

        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=stripe_signature, secret=endpoint_secret
        )

        # Handle the event
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            conversation_id = session.get("client_reference_id")
            await store_payment_status(conversation_id, "paid")
            print(f"Payment status for conversation {conversation_id} updated to 'paid'")

        elif event["type"] == "payment_method.attached":
            payment_method = event["data"]["object"]
            print(f"✅ Payment method attached: {payment_method.get('id')}")
            # Handle payment method attachment (e.g., store in your database)

        else:
            # Unexpected event type
            print(f"⚠️  Unhandled event type {event.get('type')}")

        return JSONResponse(content={"status": "success"}, status_code=200)

    except stripe.error.SignatureVerificationError as e:
        print("Invalid signature:", str(e))
        raise HTTPException(status_code=400, detail="Invalid signature")
    except json.JSONDecodeError as e:
        print("JSON decode error:", str(e))
        raise HTTPException(status_code=400, detail="Invalid payload")
    except Exception as e:
        print("Webhook error:", str(e))
        raise HTTPException(status_code=400, detail="Webhook error")

@app.get("/hasUserPaid")
async def has_user_paid(openai_conversation_id: str = Header(None)):
    """
    Check if the user has paid based on conversation ID.
    """
    if not openai_conversation_id:
        raise HTTPException(
            status_code=400, detail="Missing openai-conversation-id header"
        )

    paid_status = await retrieve_paid_status(openai_conversation_id)
    return {"paid": paid_status == "paid"}

@app.get("/privacy", response_class=HTMLResponse)
async def privacy():
    """
    Serve the privacy policy HTML content.
    """
    try:
        with open("privacy_policy.html", "r") as file:
            privacy_policy_content = file.read()
        # Replace the app name placeholder
        privacy_policy_content = privacy_policy_content.replace("{{app_name}}", app_name)
        return privacy_policy_content
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Privacy policy file not found")

@app.get("/")
async def root():
    return {"message": "Welcome to the Nexus Wire API"}

# Optionally, you can add more routes or functionalities here.

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
