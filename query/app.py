import os
import json
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
DATA_TABLE = os.environ.get("DATA_TABLE")
table = dynamodb.Table(DATA_TABLE)

def lambda_handler(event, context):
    """
    Handles secure, tenant-aware GET requests to query data from DynamoDB.
    """
    print(f"Received event: {event}")
    
    try:
        # --- NEW: Get tenant_id securely from the authorizer's claims ---
        claims = event['requestContext']['authorizer']['jwt']['claims']
        # Custom attributes in Cognito are prefixed with 'custom:'
        tenant_id = claims['custom:tenant_id']
        
        # We still get the topic from the query string
        params = event.get("queryStringParameters", {})
        topic = params.get("topic")

        if not topic:
            return {"statusCode": 400, "body": json.dumps({"error": "The 'topic' query parameter is required."})}

        print(f"Querying for tenant_id: {tenant_id} and topic: {topic}")

        # Use the highly efficient 'query' operation on DynamoDB
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"{tenant_id}#{topic}"),
            ScanIndexForward=False, # Sort by timestamp descending (newest first)
            Limit=50 # Get the 50 most recent posts
        )
        
        items = response.get("Items", [])
        print(f"Found {len(items)} items in DynamoDB.")
        
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "GET,OPTIONS"
            },
            "body": json.dumps(items)
        }
        
    except KeyError:
        # This will happen if the token is missing the tenant_id claim
        return {"statusCode": 400, "body": json.dumps({"error": "Tenant ID not found in user token."})}
    except Exception as e:
        print(f"Error querying DynamoDB: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Could not retrieve data from DynamoDB."})
        }