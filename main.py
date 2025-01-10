from flask import Flask, request, jsonify
import stripe
from sqlalchemy import create_engine, Column, String, Float, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Flask App Setup
app = Flask(__name__)

# Stripe API Setup
stripe.api_key = "sk_test_51Pn9MbDo5uWbWPXU81NQmpueBJo8XjS9NCxpxt6Z2rVNPysIZ2mR7dUZgYZvdVwq5mHOkauc89LOdfvw1zf2n2Xu00eerSOuqR"
endpoint_secret = "https://gpt-stripe-store-main-for-nexus1e.vercel.app/webhook/stripe"  # Replace with the actual webhook secret from Stripe

# Database Setup
Base = declarative_base()
engine = create_engine("sqlite:///orders.db")  # Using SQLite for simplicity
Session = sessionmaker(bind=engine)
db_session = Session()

# Order Model
class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True)
    status = Column(Enum("pending", "paid", "failed"), default="pending")
    total_amount = Column(Float)
    currency = Column(String)

# Create the database tables
Base.metadata.create_all(engine)

@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    sig = request.headers.get("stripe-signature")
    payload = request.data

    try:
        event = stripe.Webhook.construct_event(payload, sig, endpoint_secret)
    except ValueError as e:
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError as e:
        return jsonify({"error": "Invalid signature"}), 400

    # Process webhook events
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        order_id = payment_intent["metadata"].get("orderId")

        # Update order status to 'paid' in the database
        order = db_session.query(Order).filter_by(id=order_id).first()
        if order:
            order.status = "paid"
            db_session.commit()
            print(f"Order {order_id} marked as paid.")
        else:
            print(f"Order {order_id} not found.")

    elif event["type"] == "payment_intent.payment_failed":
        payment_intent = event["data"]["object"]
        order_id = payment_intent["metadata"].get("orderId")

        # Update order status to 'failed' in the database
        order = db_session.query(Order).filter_by(id=order_id).first()
        if order:
            order.status = "failed"
            db_session.commit()
            print(f"Order {order_id} marked as failed.")
        else:
            print(f"Order {order_id} not found.")

    return jsonify({"status": "success"}), 200

@app.route("/hasUserPaid/<string:order_id>", methods=["GET"])
def has_user_paid(order_id):
    order = db_session.query(Order).filter_by(id=order_id).first()

    if not order:
        return jsonify({"hasPaid": False, "message": "Order not found"}), 404

    return jsonify({"hasPaid": order.status == "paid"})

@app.route("/createOrder", methods=["POST"])
def create_order():
    data = request.json
    order_id = data.get("orderId")
    total_amount = data.get("totalAmount")
    currency = data.get("currency")

    if not all([order_id, total_amount, currency]):
        return jsonify({"error": "Missing required fields"}), 400

    # Create a new order in the database
    new_order = Order(id=order_id, total_amount=total_amount, currency=currency, status="pending")
    db_session.add(new_order)
    db_session.commit()

    return jsonify({"message": "Order created successfully", "orderId": order_id}), 201

if __name__ == "__main__":
    app.run(port=5000, debug=True)
