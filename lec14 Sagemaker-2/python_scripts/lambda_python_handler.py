"""Public front for the returns model: check a JSON order, build the row the endpoint expects, return the score."""
import base64
import json
import os

import boto3

# Which endpoint to call. Section 4 changes this setting in the console without touching the code.
ENDPOINT = os.environ.get("ENDPOINT_NAME", "leviathan-xgb-rt")
# The 18 columns prepare.py wrote, in the same order: eight numbers, then the one-hot categories.
NUMBERS = ["price", "discount_pct", "delivery_days", "customer_tenure_days",
           "prior_orders", "prior_returns", "is_gift", "seller_rating"]
CATEGORIES = ["apparel", "beauty", "books", "electronics", "footwear", "home"]
PAYMENTS = ["card", "cod", "upi", "wallet"]

runtime = boto3.client("sagemaker-runtime")


def reply(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}


def lambda_handler(event, context):
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    try:
        order = json.loads(body)
    except json.JSONDecodeError:
        return reply(400, {"error": "the body must be JSON"})
    if not isinstance(order, dict):
        return reply(400, {"error": "the body must be one JSON object"})

    missing = [name for name in NUMBERS + ["category", "payment_method"] if name not in order]
    if missing:
        return reply(400, {"error": "missing fields", "fields": missing})
    try:
        numbers = [float(order[name]) for name in NUMBERS]
    except (TypeError, ValueError):
        return reply(400, {"error": "these fields must be numbers", "fields": NUMBERS})
    if order["category"] not in CATEGORIES:
        return reply(400, {"error": "unknown category", "allowed": CATEGORIES})
    if order["payment_method"] not in PAYMENTS:
        return reply(400, {"error": "unknown payment_method", "allowed": PAYMENTS})

    row = numbers
    row += [1 if order["category"] == c else 0 for c in CATEGORIES]
    row += [1 if order["payment_method"] == p else 0 for p in PAYMENTS]
    response = runtime.invoke_endpoint(EndpointName=ENDPOINT, ContentType="text/csv",
                                       Body=",".join(str(v) for v in row))
    return reply(200, {"p_return": round(float(response["Body"].read()), 3)})