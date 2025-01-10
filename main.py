from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import stripe

# FastAPI app instance
app = FastAPI()

# Stripe setup
stripe.api_key = "sk_test_51Pn9MbDo5uWbWPXU81NQmpueBJo8XjS9NCxpxt6Z2rVNPysIZ2mR7dUZgYZvdVwq5mHOkauc89LOdfvw1zf2n2Xu00eerSOuqR"
endpoint_secret = "whsec_c5lc8jr7ijEbaMgegU5wVpt1BuQ53mKz"

# In-memory database for demonstration (replace with a real DB)
orders = {}

# Order model for creating new orders
class Order(BaseModel):
    order_id: str
    total_amount: float
    currency: str


@app.get("/openapi.json")
def get_openapi_schema():
    """
    Serves the OpenAPI JSON schema
    """
    schema = app.openapi()
    return schema


@app.post("/create-order")
async def create_order(order: Order):
    """
    API endpoint to create a new order
    """
    if order.order_id in orders:
        return {"message": f"Order with ID {order.order_id} already exists."}
    
    # Save order in the database (or in-memory for now)
    orders[order.order_id] = {
        "status": "pending",
        "total_amount": order.total_amount,
        "currency": order.currency
    }
    return {"message": "Order created successfully", "order": orders[order.order_id]}


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """
    Stripe webhook to handle payment events
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=endpoint_secret
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        order_id = payment_intent["metadata"].get("orderId")

        # Update the order in the database
        if order_id in orders:
            orders[order_id]["status"] = "paid"
            print(f"Order {order_id} marked as paid.")
        else:
            print(f"Order {order_id} not found.")

    elif event["type"] == "payment_intent.payment_failed":
        payment_intent = event["data"]["object"]
        order_id = payment_intent["metadata"].get("orderId")

        # Update the order in the database
        if order_id in orders:
            orders[order_id]["status"] = "failed"
            print(f"Order {order_id} marked as failed.")
        else:
            print(f"Order {order_id} not found.")

    return {"status": "success"}


@app.get("/has-user-paid/{order_id}")
async def has_user_paid(order_id: str):
    """
    API endpoint to check if the user has paid
    """
    order = orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return {"hasPaid": order["status"] == "paid", "order": order}
