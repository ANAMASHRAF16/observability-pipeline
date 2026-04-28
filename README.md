# Observability Pipeline

An order-processing pipeline instrumented with CloudWatch metrics, alarms, and a dashboard. Goes from "no idea what's happening" to "page me if failure rate exceeds 10%."

## Problem

The baseline pipeline has zero observability:
- `print()` statements that disappear into the void
- No latency tracking — can't tell if it's getting slower
- No failure-rate metric — can't tell if 5% or 50% of records are failing
- No alarms — operations finds out from angry users
- No dashboard — leadership has no visibility

When something breaks in production, you find out from a Slack message at 3am, not from an alarm.

## Fix

| Change | Before | After |
|---|---|---|
| Logging | `print()` | Structured JSON logs to stdout (CloudWatch Logs Insights queryable) |
| Failure tracking | None | `OrdersProcessed` and `OrdersFailed` CloudWatch counters |
| Latency tracking | None | `ProcessingLatency` metric in milliseconds, with statistics (avg, p50, p99) |
| Alarms | None | `HighFailureRate` (>10% in 5m) and `HighLatency` (p99 >500ms in 5m) |
| Dashboard | None | CloudWatch dashboard JSON with 4 widgets |
| Local dev | N/A | `METRICS_BACKEND=local` writes metrics to `metrics_local.jsonl` for testing without AWS |

## Architecture

```
orders.json → pipeline → for each order:
                          1. start timer
                          2. process
                          3. publish ProcessingLatency metric
                          4. publish OrdersProcessed or OrdersFailed counter
                          5. structured log (event=processed, order_id=..., latency_ms=...)
                                │
                                ▼
                       CloudWatch Metrics → Alarms → SNS / PagerDuty
                       CloudWatch Logs    → Insights queries
                       CloudWatch Dashboard (4 widgets)
```

## Run

```bash
pip install -r requirements.txt

# Generate sample orders (100 records, ~15% bad)
python src/generate_data.py

# Run broken version — only print output
python src/pipeline_broken.py

# Run fixed version (local backend, no AWS needed for demo)
MANIFEST_BACKEND=local python src/pipeline_fixed.py

# Run fixed version against real CloudWatch
python src/pipeline_fixed.py

# Set up alarms (one-time)
python infra/alarms.py

# Deploy dashboard (one-time)
python infra/deploy_dashboard.py

# Run tests
python tests/test_metrics.py
```

## AWS Setup

1. **IAM permissions:** the pipeline's user/role needs `cloudwatch:PutMetricData`, `cloudwatch:PutMetricAlarm`, and `cloudwatch:PutDashboard`.
2. **SNS topic** (optional): for alarm notifications, create a topic and subscribe your email. Set `ALARM_SNS_TOPIC_ARN` env var.
3. **Region:** set `AWS_REGION` (default `us-east-1`).

## Metrics published

All under namespace `OrderPipeline`.

| Metric | Unit | Dimensions | Purpose |
|---|---|---|---|
| `OrdersProcessed` | Count | `Environment` | Successful processings |
| `OrdersFailed` | Count | `Environment`, `ErrorType` | Failed processings, broken down by error type |
| `ProcessingLatency` | Milliseconds | `Environment` | Per-order processing time |

## Alarms created

| Alarm | Condition | Action |
|---|---|---|
| `OrderPipeline-HighFailureRate` | failure_rate > 10% over 5 minutes | SNS notify |
| `OrderPipeline-HighLatency` | p99 latency > 500ms over 5 minutes | SNS notify |
| `OrderPipeline-NoData` | no `OrdersProcessed` data points for 15 minutes | SNS notify (pipeline stuck) |

## Trade-offs

See PR description for the full discussion. Highlights:
- **Custom metrics cost ~$0.30/month** at our volume — negligible vs. the cost of a missed incident.
- **Metrics are batched 20 at a time** to reduce `PutMetricData` API calls (rate-limited at 150/sec/account).
- **`OrdersFailed.ErrorType` dimension** lets us see *what* is failing, not just *that* something is failing.
- **Structured JSON logs** trade human-readability for machine-queryability via CloudWatch Logs Insights.
