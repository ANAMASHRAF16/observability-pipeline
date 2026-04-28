"""
Order processing pipeline - FIXED version (full observability).

What changed vs. broken:
- Replaced print() with structured JSON logs (CloudWatch Logs Insights queryable)
- Added latency tracking around each process_order call
- Added OrdersProcessed and OrdersFailed counter metrics
- OrdersFailed is dimensioned on ErrorType so we can see *what* is failing
- Metrics batched and flushed on shutdown

Design notes:
- The instrumentation is a thin wrapper around the existing logic. The
  business code (process_order) is unchanged — observability is added
  at the orchestration layer, not threaded through internals.
- Failure counts are dimensioned on ErrorType (e.g. "missing_user",
  "invalid_amount") so dashboards can show which class of error spiked.
- Logs use a single JSON object per line so CloudWatch Logs Insights can
  parse them with `fields @timestamp, event, order_id, latency_ms`.
"""

import json
import logging
import os
import random
import sys
import time

from metrics import client as metrics_client, time_block

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUT_PATH = os.path.join(DATA_DIR, "output", "processed_fixed.json")
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)


# ---------- Structured logging ----------

class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)
        return json.dumps(payload)


def _make_logger():
    logger = logging.getLogger("pipeline")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


log = _make_logger()


def log_event(event, **fields):
    record = log.makeRecord("pipeline", logging.INFO, "", 0, event, (), None)
    record.extra_fields = {"event": event, **fields}
    log.handle(record)


# ---------- Business logic (unchanged) ----------

def process_order(order):
    time.sleep(random.uniform(0.01, 0.05))

    if order.get("user_id") is None:
        raise ValueError("missing_user")
    if not isinstance(order.get("amount"), (int, float)):
        raise ValueError("invalid_amount_type")
    if order["amount"] <= 0:
        raise ValueError("non_positive_amount")

    return {
        "order_id": order["order_id"],
        "user_id": order["user_id"],
        "amount_usd": order["amount"],
        "status": "processed",
    }


# ---------- Orchestration with observability ----------

def run_pipeline():
    metrics = metrics_client()

    with open(os.path.join(DATA_DIR, "orders.json"), "r", encoding="utf-8") as f:
        orders = json.load(f)

    log_event("pipeline_started", total_orders=len(orders))
    processed = []
    failed = 0

    for order in orders:
        order_id = order.get("order_id", "unknown")

        try:
            with time_block("ProcessingLatency"):
                result = process_order(order)

            processed.append(result)
            metrics.publish("OrdersProcessed", 1)
            log_event("order_processed", order_id=order_id)

        except Exception as e:
            failed += 1
            error_type = str(e) if isinstance(e, ValueError) else "unexpected"
            metrics.publish("OrdersFailed", 1, dimensions={"ErrorType": error_type})
            log_event("order_failed", order_id=order_id, error_type=error_type)

    metrics.flush()

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2)

    failure_rate = failed / len(orders) if orders else 0
    log_event(
        "pipeline_completed",
        total=len(orders),
        processed=len(processed),
        failed=failed,
        failure_rate=round(failure_rate, 4),
    )

    return {"total": len(orders), "processed": len(processed), "failed": failed}


if __name__ == "__main__":
    run_pipeline()
