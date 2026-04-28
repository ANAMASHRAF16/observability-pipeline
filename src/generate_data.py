"""
Generate sample order records to feed the pipeline.

Mixes valid and intentionally-bad records so the pipeline produces
realistic failure-rate metrics.
"""

import json
import os
import random

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

random.seed(42)

orders = []
for i in range(100):
    valid = random.random() > 0.15  # ~15% bad records
    if valid:
        orders.append({
            "order_id": f"ORD-{i:04d}",
            "user_id": f"USR-{random.randint(1, 50):03d}",
            "amount": round(random.uniform(10, 500), 2),
            "currency": "USD",
        })
    else:
        orders.append({
            "order_id": f"ORD-{i:04d}",
            "user_id": None,
            "amount": -1 if random.random() < 0.5 else "not-a-number",
            "currency": "USD",
        })

out_path = os.path.join(DATA_DIR, "orders.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(orders, f, indent=2)

print(f"Wrote {len(orders)} orders to {out_path}")
