import os
import json
import boto3
from boto3.dynamodb.conditions import Attr

sns_client = boto3.client("sns")
dynamodb = boto3.resource("dynamodb")

TENANTS_TABLE_NAME = os.environ.get("TENANTS_TABLE_NAME")
JOB_TOPIC_ARN = os.environ.get("JOB_TOPIC_ARN")
tenants_table = dynamodb.Table(TENANTS_TABLE_NAME)

def get_active_tenants():
    print("Fetching active tenants from DynamoDB...")
    response = tenants_table.scan(FilterExpression=Attr('is_active').eq(True))
    tenants = response.get('Items', [])
    print(f"Found {len(tenants)} active tenants.")
    return tenants

def lambda_handler(event, context):
    """
    Scans for active tenants and publishes a "collection job" message to SNS
    for each item on each tenant's watchlist.
    """
    print("Dispatcher Lambda invoked.")
    active_tenants = get_active_tenants()
    job_count = 0

    for tenant in active_tenants:
        tenant_id = tenant['tenant_id']
        watchlist = tenant.get('watchlist', [])

        for item in watchlist:
            job_payload = {
                "tenant_id": tenant_id,
                "source": item.get("source"),
                "topic": item.get("topic")
            }

            try:
                sns_client.publish(
                    TopicArn=JOB_TOPIC_ARN,
                    Message=json.dumps(job_payload),
                    MessageStructure='string'
                )
                job_count += 1
            except Exception as e:
                print(f"Failed to publish job for tenant {tenant_id}, topic {item.get('topic')}. Error: {e}")

    print(f"Successfully published {job_count} collection jobs.")
    return {"statusCode": 200, "body": f"Published {job_count} jobs."}