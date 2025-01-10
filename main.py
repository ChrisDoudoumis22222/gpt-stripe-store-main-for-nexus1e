import os
import stripe
import aioredis
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from fastapi.openapi.utils import get_openapi

# Load environment variables
load_dotenv()

# Stripe and app setup
stripe.api_key = "sk_test_51Pn9MbDo5uWbWPXU81NQmpueBJo8XjS9NCxpxt6Z2rVNPysIZ2mR7dUZgYZvdVwq5mHOkauc89LOdfvw1zf2n2Xu00eerSOuqR"
endpoint_secret = "whsec_c5lc8jr7ijEbaMgegU5wVpt1BuQ53mKz"
payment_link = "https://buy.stripe.com/test_aEUeYSdZEaR9b7O288"
redis_url = "redis://default:mS32jrbheJx1HUHuqkhQ8QGWyQpJTB0@redis-15159.c243.eu-west-1-3.ec2.redns.redis-cloud.com:15159"
app_url = "https://gpt-stripe-store-main-for-nexus1e.vercel.app/"
app_name = "Nexus wire"

# Initialize FastAPI app
app = FastAPI(
    servers=[
        {
            "url": app_url,
            "description": "Production environment",
        },
    ]
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
        title="Nexus Wire API",
        version="1.0.0",
        description="API for managing Stripe payments and Redis-based payment status tracking.",
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
    return f"Tell the user to click here: {url}, and type 'continue' when they're done."


@app.post("/webhook/stripe")
async def webhook_received(request: Request, stripe_signature: str = Header(None)):
    """
    Handle Stripe webhook events.
    """
    try:
        payload = request.state.body  # Access raw body from middleware
        print("Payload:", payload)  # Debug: Log payload

        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=stripe_signature, secret=endpoint_secret
        )

        # Process the event
        if event["type"] == "checkout.session.completed":
            conversation_id = event["data"]["object"]["client_reference_id"]
            await store_payment_status(conversation_id, "paid")
            print(f"Payment status for conversation {conversation_id} updated to 'paid'")

        return {"status": "success"}

    except stripe.error.SignatureVerificationError as e:
        print("Signature error:", str(e))
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print("Error:", str(e))
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
