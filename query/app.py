import os
import json
import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timedelta, timezone
from decimal import Decimal

dynamodb = boto3.resource("dynamodb")
DATA_TABLE_NAME = os.environ.get("DATA_TABLE")
table = dynamodb.Table(DATA_TABLE_NAME)

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal): return float(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    """
    Handles secure, tenant-aware GET requests to query data from DynamoDB.
    Supports fetching the latest items OR items within a date range.
    """
    print(f"Received event: {event}")
    
    try:
        claims = event['requestContext']['authorizer']['jwt']['claims']
        tenant_id = claims['custom:tenant_id']
        
        params = event.get("queryStringParameters", {})
        topic = params.get("topic")
        start_date = params.get("start_date")
        end_date = params.get("end_date")

        if not topic:
            return {"statusCode": 400, "body": json.dumps({"error": "The 'topic' query parameter is required."})}

        pk = f"{tenant_id}#{topic}"
        query_params = {
            "KeyConditionExpression": Key("PK").eq(pk),
            "ScanIndexForward": False,
        }

        # --- NEW: Date Range Logic ---
        if start_date and end_date:
            print(f"Querying for PK: {pk} between {start_date} and {end_date}")
            query_params["KeyConditionExpression"] &= Key("SK").between(start_date, end_date)
            query_params["ScanIndexForward"] = True
            query_params["Limit"] = 1000
        else:
            print(f"Querying for latest items for PK: {pk}")
            query_params["Limit"] = 50

        response = table.query(**query_params)
        items = response.get("Items", [])
        
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,Authorization",
                "Access-Control-Allow-Methods": "GET,OPTIONS"
            },
            "body": json.dumps(items, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error querying DynamoDB: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": "Could not retrieve data from DynamoDB."})}