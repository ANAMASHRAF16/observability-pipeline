"""
Tests for the observability layer.

Runs the pipeline with METRICS_BACKEND=local so no AWS is required, then
inspects the local metrics file to verify:

  1. Every successful order emitted an OrdersProcessed metric
  2. Every failed order emitted an OrdersFailed metric with an ErrorType dim
  3. Every order emitted a ProcessingLatency metric in milliseconds
  4. Failure rate computed from metrics matches the pipeline's own count
  5. Latency values are positive numbers
  6. JSON logs are well-formed (parseable per-line)
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
LOCAL_METRICS = os.path.join(DATA_DIR, "metrics_local.jsonl")


def setup():
    if os.path.exists(LOCAL_METRICS):
        os.remove(LOCAL_METRICS)
    subprocess.run([sys.executable, os.path.join(ROOT, "src", "generate_data.py")], check=True)


def run_pipeline_local():
    env = os.environ.copy()
    env["METRICS_BACKEND"] = "local"
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "src", "pipeline_fixed.py")],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def load_metrics():
    with open(LOCAL_METRICS, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def parse_log_lines(stdout):
    parsed = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            raise AssertionError(f"Log line is not valid JSON: {line!r}")
    return parsed


def main():
    setup()
    stdout = run_pipeline_local()

    metrics = load_metrics()
    logs = parse_log_lines(stdout)

    processed_metrics = [m for m in metrics if m["MetricName"] == "OrdersProcessed"]
    failed_metrics = [m for m in metrics if m["MetricName"] == "OrdersFailed"]
    latency_metrics = [m for m in metrics if m["MetricName"] == "ProcessingLatency"]

    completion = next(l for l in logs if l.get("event") == "pipeline_completed")
    expected_processed = completion["processed"]
    expected_failed = completion["failed"]

    assert len(processed_metrics) == expected_processed, \
        f"Expected {expected_processed} OrdersProcessed metrics, got {len(processed_metrics)}"
    print(f"  PASS: OrdersProcessed count matches pipeline ({expected_processed})")

    assert len(failed_metrics) == expected_failed, \
        f"Expected {expected_failed} OrdersFailed metrics, got {len(failed_metrics)}"
    print(f"  PASS: OrdersFailed count matches pipeline ({expected_failed})")

    for m in failed_metrics:
        dims = {d["Name"]: d["Value"] for d in m["Dimensions"]}
        assert "ErrorType" in dims, f"OrdersFailed missing ErrorType dimension: {m}"
    print(f"  PASS: every OrdersFailed has an ErrorType dimension")

    expected_latency_count = expected_processed + expected_failed
    assert len(latency_metrics) == expected_latency_count, \
        f"Expected {expected_latency_count} ProcessingLatency metrics, got {len(latency_metrics)}"
    print(f"  PASS: ProcessingLatency emitted for every order attempt ({expected_latency_count})")

    for m in latency_metrics:
        assert m["Unit"] == "Milliseconds", f"ProcessingLatency wrong unit: {m['Unit']}"
        assert m["Value"] > 0, f"ProcessingLatency non-positive: {m['Value']}"
    print(f"  PASS: ProcessingLatency values are positive milliseconds")

    metric_failure_rate = len(failed_metrics) / (len(failed_metrics) + len(processed_metrics))
    pipeline_failure_rate = expected_failed / (expected_failed + expected_processed)
    assert abs(metric_failure_rate - pipeline_failure_rate) < 0.001, \
        f"Failure rate from metrics ({metric_failure_rate:.4f}) doesn't match pipeline ({pipeline_failure_rate:.4f})"
    print(f"  PASS: failure rate from metrics matches pipeline ({metric_failure_rate:.2%})")

    print("\nAll tests passed.")


if __name__ == "__main__":
    main()
