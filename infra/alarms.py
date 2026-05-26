"""
Create CloudWatch alarms for the pipeline.

Run once to set up:
  python infra/alarms.py

Alarms:
  - HighFailureRate: failure rate > 10% over 5 minutes
  - HighLatency:     p99 latency > 500ms over 5 minutes
  - NoData:          no OrdersProcessed for 15 minutes (pipeline stuck)

All alarms publish to the SNS topic in ALARM_SNS_TOPIC_ARN if set.
"""

import os

import boto3

NAMESPACE = os.environ.get("METRICS_NAMESPACE", "OrderPipeline")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
SNS_TOPIC_ARN = os.environ.get("ALARM_SNS_TOPIC_ARN")
REGION = os.environ.get("AWS_REGION", "us-east-1")

cw = boto3.client("cloudwatch", region_name=REGION)


def env_dim():
    return [{"Name": "Environment", "Value": ENVIRONMENT}]


def alarm_actions():
    return [SNS_TOPIC_ARN] if SNS_TOPIC_ARN else []


# Known ErrorType values published by src/pipeline_fixed.py. Keeping this
# as a fixed enum (not raw exception strings) is the cost-bounded design
# choice from PR 1 - and it also lets the alarm enumerate them explicitly
# below, since CloudWatch alarms do NOT support SEARCH expressions
# (only dashboards do). If a new ErrorType is added to the pipeline,
# add it here too.
ERROR_TYPES = ["missing_user", "invalid_amount_type", "non_positive_amount", "unexpected"]


def _failed_metric_stat(error_type_value: str, metric_id: str) -> dict:
    """One MetricStat block matching OrdersFailed for a specific ErrorType."""
    return {
        "Id": metric_id,
        "MetricStat": {
            "Metric": {
                "Namespace": NAMESPACE,
                "MetricName": "OrdersFailed",
                "Dimensions": env_dim() + [{"Name": "ErrorType", "Value": error_type_value}],
            },
            "Period": 300,
            "Stat": "Sum",
        },
        "ReturnData": False,
    }


def create_high_failure_rate_alarm():
    # CloudWatch alarms can't use SEARCH, so we query OrdersFailed once per
    # known ErrorType and sum them with FILL(_, 0) to treat missing data as 0.
    failed_ids = [f"f{i}" for i in range(len(ERROR_TYPES))]
    failed_metric_stats = [
        _failed_metric_stat(et, fid) for et, fid in zip(ERROR_TYPES, failed_ids)
    ]
    sum_failed = " + ".join(f"FILL({fid}, 0)" for fid in failed_ids)

    cw.put_metric_alarm(
        AlarmName=f"{NAMESPACE}-HighFailureRate",
        AlarmDescription="Failure rate exceeded 10% over 5 minutes",
        ActionsEnabled=True,
        AlarmActions=alarm_actions(),
        EvaluationPeriods=1,
        DatapointsToAlarm=1,
        Threshold=0.10,
        ComparisonOperator="GreaterThanThreshold",
        TreatMissingData="notBreaching",
        Metrics=[
            {
                "Id": "failure_rate",
                "Expression": f"({sum_failed}) / (FILL(processed, 0) + ({sum_failed}))",
                "Label": "Failure Rate",
                "ReturnData": True,
            },
            {
                "Id": "processed",
                "MetricStat": {
                    "Metric": {
                        "Namespace": NAMESPACE,
                        "MetricName": "OrdersProcessed",
                        "Dimensions": env_dim(),
                    },
                    "Period": 300,
                    "Stat": "Sum",
                },
                "ReturnData": False,
            },
            *failed_metric_stats,
        ],
    )
    print(f"  created {NAMESPACE}-HighFailureRate")


def create_high_latency_alarm():
    cw.put_metric_alarm(
        AlarmName=f"{NAMESPACE}-HighLatency",
        AlarmDescription="p99 processing latency exceeded 500ms over 5 minutes",
        ActionsEnabled=True,
        AlarmActions=alarm_actions(),
        Namespace=NAMESPACE,
        MetricName="ProcessingLatency",
        Dimensions=env_dim(),
        ExtendedStatistic="p99",
        Period=300,
        EvaluationPeriods=1,
        Threshold=500,
        ComparisonOperator="GreaterThanThreshold",
        TreatMissingData="notBreaching",
    )
    print(f"  created {NAMESPACE}-HighLatency")


def create_no_data_alarm():
    cw.put_metric_alarm(
        AlarmName=f"{NAMESPACE}-NoData",
        AlarmDescription="No OrdersProcessed metric for 15 minutes - pipeline stuck",
        ActionsEnabled=True,
        AlarmActions=alarm_actions(),
        Namespace=NAMESPACE,
        MetricName="OrdersProcessed",
        Dimensions=env_dim(),
        Statistic="Sum",
        Period=900,
        EvaluationPeriods=1,
        Threshold=1,
        ComparisonOperator="LessThanThreshold",
        TreatMissingData="breaching",
    )
    print(f"  created {NAMESPACE}-NoData")


def main():
    print(f"Creating alarms in {REGION}, namespace={NAMESPACE}, env={ENVIRONMENT}")
    if not SNS_TOPIC_ARN:
        print("  WARNING: ALARM_SNS_TOPIC_ARN not set - alarms will fire but not notify")

    create_high_failure_rate_alarm()
    create_high_latency_alarm()
    create_no_data_alarm()
    print("Done.")


if __name__ == "__main__":
    main()
