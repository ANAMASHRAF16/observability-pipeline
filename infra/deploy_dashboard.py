"""
Deploy the CloudWatch dashboard from dashboard.json.

Run once after creating alarms:
  python infra/deploy_dashboard.py
"""

import json
import os

import boto3

DASHBOARD_NAME = os.environ.get("DASHBOARD_NAME", "OrderPipeline")
REGION = os.environ.get("AWS_REGION", "us-east-1")

cw = boto3.client("cloudwatch", region_name=REGION)

dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.json")
with open(dashboard_path, "r", encoding="utf-8") as f:
    body = f.read()

# rewrite region in the JSON if the env disagrees with the file's default
if REGION != "us-east-1":
    body = body.replace('"region": "us-east-1"', f'"region": "{REGION}"')

resp = cw.put_dashboard(DashboardName=DASHBOARD_NAME, DashboardBody=body)
validation = resp.get("DashboardValidationMessages", [])

if validation:
    print("Validation warnings:")
    for v in validation:
        print(f"  {v}")
else:
    print(f"Deployed dashboard '{DASHBOARD_NAME}' to region {REGION}")
    print(f"  https://{REGION}.console.aws.amazon.com/cloudwatch/home?region={REGION}#dashboards:name={DASHBOARD_NAME}")
