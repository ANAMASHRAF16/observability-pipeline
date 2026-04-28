"""
CloudWatch metrics publisher with batching and a local-file fallback.

Two backends:
- cloudwatch (default) — boto3 PutMetricData, batches up to 20 per call
- local                 — appends to data/metrics_local.jsonl for offline demo

Both implement the same publish() / flush() contract so the pipeline code
doesn't care which is in use.

Why batching: CloudWatch PutMetricData is rate-limited to 150 transactions
per second per account, and each call accepts up to 20 metric data points.
Sending one metric per call burns the rate limit unnecessarily.
"""

import json
import os
import time
from collections import deque
from datetime import datetime, timezone

NAMESPACE = os.environ.get("METRICS_NAMESPACE", "OrderPipeline")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
BACKEND = os.environ.get("METRICS_BACKEND", "cloudwatch").lower()
BATCH_SIZE = 20

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
LOCAL_METRICS_FILE = os.path.join(DATA_DIR, "metrics_local.jsonl")


class MetricsClient:
    def __init__(self):
        self._buffer = deque()
        self._cw = None
        if BACKEND == "cloudwatch":
            import boto3
            self._cw = boto3.client(
                "cloudwatch",
                region_name=os.environ.get("AWS_REGION", "us-east-1"),
            )

    def publish(self, name, value, unit="Count", dimensions=None):
        """Buffer a metric. Auto-flushes when buffer hits BATCH_SIZE."""
        dims = [{"Name": "Environment", "Value": ENVIRONMENT}]
        if dimensions:
            dims.extend({"Name": k, "Value": v} for k, v in dimensions.items())

        self._buffer.append({
            "MetricName": name,
            "Value": value,
            "Unit": unit,
            "Timestamp": datetime.now(timezone.utc),
            "Dimensions": dims,
        })

        if len(self._buffer) >= BATCH_SIZE:
            self.flush()

    def flush(self):
        """Send buffered metrics to the backend."""
        if not self._buffer:
            return

        batch = []
        while self._buffer and len(batch) < BATCH_SIZE:
            batch.append(self._buffer.popleft())

        if BACKEND == "cloudwatch":
            self._cw.put_metric_data(Namespace=NAMESPACE, MetricData=batch)
        else:
            with open(LOCAL_METRICS_FILE, "a", encoding="utf-8") as f:
                for m in batch:
                    record = {**m, "Timestamp": m["Timestamp"].isoformat()}
                    f.write(json.dumps(record) + "\n")


_default_client = None


def client():
    global _default_client
    if _default_client is None:
        _default_client = MetricsClient()
    return _default_client


def time_block(name, dimensions=None):
    """Context manager that publishes a latency metric on exit."""
    return _LatencyTimer(name, dimensions)


class _LatencyTimer:
    def __init__(self, name, dimensions):
        self.name = name
        self.dimensions = dimensions

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        client().publish(self.name, elapsed_ms, unit="Milliseconds", dimensions=self.dimensions)
