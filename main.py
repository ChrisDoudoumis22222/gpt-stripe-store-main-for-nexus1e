#!/usr/bin/env python3.11
# Python 3.11 or newer required.

import json
import stripe
import redis.asyncio as redis
from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from fastapi.openapi.utils import get_openapi
from pydantic import BaseSettings, AnyUrl, Field
import logging
import uvicorn
from typing import Optional
import aiofiles

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration Class with Embedded Variables
class Settings(BaseSettings):
    # Stripe Configuration
    STRIPE_API_KEY: str = "sk_test_51Pn9MbDo5uWbWPXU81NQmpueBJo8XjS9NCxpxt6Z2rVNPysIZ2mR7dUZgYZvdVwq5mHOkauc89LOdfvw1zf2n2Xu00eerSOuqR"
    STRIPE_ENDPOINT_SECRET: str = "whsec_c5lc8jr7ijEbaMgegU5wVpt1BuQ53mKz"
    STRIPE_PRODUCT_ID: str = "we_1QfSOPDo5uWbWPXUoR9sz0kD"
    STRIPE_PAYMENT_LINK: AnyUrl = "https://buy.stripe.com/test_aEUeYSdZEaR9b7O288"

    # Redis Configuration
    REDIS_URL: AnyUrl = "redis://default:mS32jrbheJx1HUHuqkhQ8QGWyQpJTB0@redis-15159.c243.eu-west-1-3.ec2.redns.redis-cloud.com:15159"

    # Application Configuration
    APP_URL: AnyUrl = "https://gpt-stripe-store-main-for-nexus1e.vercel.app/"
    APP_NAME: str = "Nexus Wire"

    class Config:
        # No env_file since variables are embedded
        case_sensitive = True

# Initialize settings
settings = Settings()

# Initialize Stripe
stripe.api_key = settings.STRIPE_API_KEY
endpoint_secret = settings.STRIPE_ENDPOINT_SECRET
product_id = settings.STRIPE_PRODUCT_ID
payment_link = settings.STRIPE_PAYMENT_LINK
redis_url = settings.REDIS_URL
app_url = settings.APP_URL
app_name = settings.APP_NAME

# Initialize FastAPI app
app = FastAPI(
    servers=[
        {
            "url": str(app_url),
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
redis_client: Optional[redis.Redis] = None

async def get_redis_connection() -> redis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(redis_url, decode_responses=True)
        logger.info("Connected to Redis")
    return redis_client

# Helper functions for storing and retrieving payment statuses
async def store_payment_status(conversation_id: str, status: str) -> None:
    """
    Store payment status in Redis.
    """
    redis_conn = await get_redis_connection()
    await redis_conn.set(conversation_id, status)
    logger.debug(f"Stored payment status for {conversation_id}: {status}")

async def retrieve_paid_status(conversation_id: str) -> Optional[str]:
    """
    Retrieve payment status from Redis.
    """
    redis_conn = await get_redis_connection()
    status = await redis_conn.get(conversation_id)
    logger.debug(f"Retrieved payment status for {conversation_id}: {status}")
    return status

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

# Dependency to extract the openai_conversation_id from headers
async def get_conversation_id(
    openai_conversation_id: Optional[str] = Header(None, alias="openai-conversation-id")
) -> str:
    if not openai_conversation_id:
        logger.warning("Missing openai-conversation-id header")
        raise HTTPException(
            status_code=400, detail="Missing openai-conversation-id header"
        )
    return openai_conversation_id

# Routes
@app.get("/getPaymentURL", summary="Generate Payment URL")
async def get_payment_url(conversation_id: str = Depends(get_conversation_id)):
    """
    Generate and return a payment URL with a client_reference_id.
    """
    url = f"{payment_link}?client_reference_id={conversation_id}"
    logger.info(f"Generated payment URL for {conversation_id}: {url}")
    return {
        "message": "Please click the link to proceed with your payment. Type 'continue' once done.",
        "url": url
    }

@app.post("/webhook/stripe", summary="Stripe Webhook Endpoint")
async def webhook_received(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature")
):
    """
    Handle Stripe webhook events.
    """
    try:
        payload = await request.body()
        logger.debug(f"Received Stripe webhook with payload: {payload}")

        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=stripe_signature, secret=endpoint_secret
        )

        # Handle the event
        event_type = event.get("type")
        logger.info(f"Handling Stripe event type: {event_type}")

        if event_type == "checkout.session.completed":
            session = event["data"]["object"]
            conversation_id = session.get("client_reference_id")
            if conversation_id:
                await store_payment_status(conversation_id, "paid")
                logger.info(f"Payment status for conversation {conversation_id} updated to 'paid'")
            else:
                logger.warning("No client_reference_id found in the session object")

        elif event_type == "payment_method.attached":
            payment_method = event["data"]["object"]
            payment_method_id = payment_method.get("id")
            logger.info(f"✅ Payment method attached: {payment_method_id}")
            # Handle payment method attachment (e.g., store in your database)

        else:
            logger.warning(f"⚠️ Unhandled event type: {event_type}")

        return JSONResponse(content={"status": "success"}, status_code=200)

    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid Stripe signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=400, detail="Webhook processing error")

@app.get("/hasUserPaid", summary="Check Payment Status")
async def has_user_paid(conversation_id: str = Depends(get_conversation_id)):
    """
    Check if the user has paid based on conversation ID.
    """
    paid_status = await retrieve_paid_status(conversation_id)
    is_paid = paid_status == "paid"
    logger.info(f"Payment status for {conversation_id}: {'paid' if is_paid else 'not paid'}")
    return {"paid": is_paid}

@app.get("/privacy", response_class=HTMLResponse, summary="Privacy Policy")
async def privacy():
    """
    Serve the privacy policy HTML content.
    """
    try:
        async with aiofiles.open("privacy_policy.html", "r") as file:
            privacy_policy_content = await file.read()
        # Replace the app name placeholder
        privacy_policy_content = privacy_policy_content.replace("{{app_name}}", app_name)
        logger.info("Served privacy policy")
        return privacy_policy_content
    except FileNotFoundError:
        logger.error("Privacy policy file not found")
        raise HTTPException(status_code=404, detail="Privacy policy file not found")
    except Exception as e:
        logger.error(f"Error serving privacy policy: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/", summary="Root Endpoint")
async def root():
    return {"message": f"Welcome to the {app_name} API"}

# Optionally, you can add more routes or functionalities here.

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
