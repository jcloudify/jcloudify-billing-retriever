import json
import boto3
import os
from datetime import datetime


API_EVENT_SOURCE = "app.jcloudify.billing.retriever.event"
API_EVENT_DETAIL_TYPE = "app.jcloudify.billing.retriever"


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


def get_formatted_billing_info(
    app_name, env, start_period, end_period, total, currency
):
    return {
        "app_name": app_name,
        "env": env,
        "start_period": start_period,
        "end_period": end_period,
        "total cost": total + " " + currency,
    }


def get_billing_by_app_and_env(app_name, env_name, start, end):
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
                    "Values": [app_name],
                    "MatchOptions": [
                        "EQUALS",
                    ],
                }
            },
            {
                "Tags": {
                    "Key": "env",
                    "Values": [env_name],
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


def handle_sqs_message(event):
    today = datetime.now()
    first_day_of_current_month = today.replace(day=1)
    first_day_of_previous_month = first_day_last_month(first_day_of_current_month)
    print(
        f"Retrieving app billing info from {first_day_of_previous_month} to {first_day_of_current_month}"
    )

    app_tag_values = list(get_tag_values("app"))
    env_tag_values = list(get_tag_values("env"))

    app_billings = []

    for app_name in app_tag_values:
        for env_name in env_tag_values:
            response = get_billing_by_app_and_env(
                app_name,
                env_name,
                first_day_of_previous_month,
                first_day_of_current_month,
            )
            for result in response["ResultsByTime"]:
                amount = result["Total"]["UnblendedCost"]["Amount"]
                currency = result["Total"]["UnblendedCost"]["Unit"]
                app_billings.append(
                    get_formatted_billing_info(
                        app_name,
                        env_name,
                        first_day_of_previous_month,
                        first_day_of_current_month,
                        amount,
                        currency,
                    )
                )

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "SQS messages processed successfully!"}),
    }


def handle_api_request(event):
    event_bus_name = os.getenv("AWS_EVENTBRIDGE_BUS")
    eventbridge_client = boto3.client("events")
    response = eventbridge_client.put_events(
        Entries=[
            {
                "Source": API_EVENT_SOURCE,
                "DetailType": API_EVENT_DETAIL_TYPE,
                "Detail": json.dumps(API_EVENT_DETAIL_TYPE),
                "EventBusName": event_bus_name,
            },
        ]
    )
    failed_entry_count = response["FailedEntryCount"]
    if failed_entry_count > 0:
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "message": "An error occurred when trying to trigger billing retrieval."
                }
            ),
        }
    else:
        return {
            "statusCode": 200,
            "body": json.dumps(
                {"message": "Billing retrieval successfully triggered!"}
            ),
        }


def lambda_handler(event, context):
    if "httpMethod" in event:
        return handle_api_request(event)

    if "Records" in event and event["Records"][0]["eventSource"] == "aws:sqs":
        for records in event["Records"]:
            print(f"Received records: {json.dumps(records)}")
            body = json.loads(records["body"])
            detail_type = body["detail-type"]
            if detail_type == API_EVENT_DETAIL_TYPE:
                return handle_sqs_message(event)

    return {"statusCode": 400, "body": json.dumps({"message": "Unknown event source"})}
