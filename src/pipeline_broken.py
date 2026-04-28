"""
Order processing pipeline - BROKEN version (no observability).

PROBLEMS:
- Uses print() — output disappears, can't query, can't alarm on it
- No latency tracking — can't tell if processing is slowing down
- No failure-rate metric — can't tell if 5% or 50% of records are failing
- No alarms — operations team finds out about problems from angry users
- No dashboard — leadership has no visibility into pipeline health

If this runs in production at 3am and 80% of records fail, nobody knows
until tomorrow morning when someone notices revenue is down.
"""

import json
import os
import random
import time

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUT_PATH = os.path.join(DATA_DIR, "output", "processed_broken.json")
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)


def process_order(order):
    """Validate and enrich a single order."""
    time.sleep(random.uniform(0.01, 0.05))

    if order.get("user_id") is None:
        raise ValueError("missing user_id")
    if not isinstance(order.get("amount"), (int, float)):
        raise ValueError(f"invalid amount: {order.get('amount')}")
    if order["amount"] <= 0:
        raise ValueError(f"non-positive amount: {order['amount']}")

    return {
        "order_id": order["order_id"],
        "user_id": order["user_id"],
        "amount_usd": order["amount"],
        "status": "processed",
    }


def run_pipeline():
    with open(os.path.join(DATA_DIR, "orders.json"), "r", encoding="utf-8") as f:
        orders = json.load(f)

    print(f"Processing {len(orders)} orders...")
    processed = []

    for order in orders:
        try:
            result = process_order(order)
            processed.append(result)
        except Exception as e:
            print(f"FAILED {order.get('order_id')}: {e}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2)

    print(f"Done. Wrote {len(processed)} processed orders.")


if __name__ == "__main__":
    run_pipeline()
