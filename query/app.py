import os
import json
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
DATA_TABLE = os.environ.get("DATA_TABLE")
table = dynamodb.Table(DATA_TABLE)

def lambda_handler(event, context):
    """
    Handles GET requests to query data from DynamoDB for the dashboard.
    """
    print(f"Received event: {event}")
    
    # Extract query string parameters
    params = event.get("queryStringParameters", {})
    tenant_id = params.get("tenant_id", "default-tenant")
    topic = params.get("topic", "general")

    if not all([tenant_id, topic]):
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "tenant_id and topic are required query parameters."})
        }

    try:
        # Use the highly efficient 'query' operation on DynamoDB
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"{tenant_id}#{topic}"),
            ScanIndexForward=False, # Sort by timestamp descending (newest first)
            Limit=20 # Get the 20 most recent posts
        )
        
        items = response.get("Items", [])
        print(f"Found {len(items)} items in DynamoDB.")
        
        return {
            "statusCode": 200,
            # Add CORS headers to allow browser access
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET"
            },
            "body": json.dumps(items)
        }
        
    except Exception as e:
        print(f"Error querying DynamoDB: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Could not retrieve data from DynamoDB."})
        }