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


def create_high_failure_rate_alarm():
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
                "Expression": "failed / (processed + failed)",
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
            {
                # Aggregate OrdersFailed across all ErrorType dimension values.
                # The metric is published with Environment + ErrorType dimensions,
                # so a single-dimension MetricStat query (only Environment) finds
                # nothing and returns 0 - making failure_rate stuck at 0%.
                # SEARCH sums every ErrorType variant under Environment=<env>.
                "Id": "failed",
                "Expression": "SUM(SEARCH('{" + NAMESPACE + ",Environment,ErrorType} MetricName=\"OrdersFailed\" Environment=\"" + ENVIRONMENT + "\"', 'Sum', 300))",
                "Label": "Failed (all error types)",
                "ReturnData": False,
            },
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
