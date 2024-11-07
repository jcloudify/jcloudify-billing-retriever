import json
from datetime import datetime

import boto3


def first_day_last_month(date):
    last_month = date.month - 1 if date.month > 1 else 12
    year_of_last_month = date.year if date.month > 1 else date.year - 1
    return date.replace(year=year_of_last_month, month=last_month, day=1)


def get_tag_values(tag_key):
    resource_group_client = boto3.client(
        "resourcegroupstaggingapi", region_name="eu-west-3"
    )
    response = resource_group_client.get_resources(TagFilters=[{"Key": tag_key}])
    tag_values = {
        tag["Value"]
        for resource in response["ResourceTagMappingList"]
        for tag in resource["Tags"]
        if tag["Key"] == tag_key
    }
    return tag_values


def get_billing_by_app_and_env(app_names, env_names, start, end):
    cost_explorer_client = boto3.client("ce", region_name="eu-west-3")
    time_period = {
        "Start": start.strftime("%Y-%m-%d"),
        "End": end.strftime("%Y-%m-%d"),
    }
    tag_filters = {
        "And": [
            {
                "Tags": {
                    "Key": "app",
                    "Values": app_names,
                    "MatchOptions": [
                        "EQUALS",
                    ],
                }
            },
            {
                "Tags": {
                    "Key": "env",
                    "Values": env_names,
                    "MatchOptions": [
                        "EQUALS",
                    ],
                }
            },
        ]
    }
    response = cost_explorer_client.get_cost_and_usage(
        TimePeriod=time_period,
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        Filter=tag_filters,
    )
    return response


def lambda_handler(event, context):
    today = datetime.now()
    first_day_of_current_month = today.replace(day=1)
    first_day_of_previous_month = first_day_last_month(first_day_of_current_month)

    app_tag_values = get_tag_values("app")
    env_tag_values = get_tag_values("env")
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "type": str(type(app_tag_values)),
                "app_tag_Values": str(app_tag_values),
                "env_tag_Values": str(env_tag_values),
            }
        ),
    }
