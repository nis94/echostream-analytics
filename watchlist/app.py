# In watchlist/app.py
import os
import json
import boto3

dynamodb = boto3.resource("dynamodb")
TENANTS_TABLE_NAME = os.environ.get("TENANTS_TABLE_NAME")
tenants_table = dynamodb.Table(TENANTS_TABLE_NAME)

def lambda_handler(event, context):
    """
    Handles secure POST requests to update a tenant's watchlist (subreddits)
    and tenant_name.
    """
    print(f"Received event: {event}")
    
    try:
        # Get the tenant_id securely from the user's validated token
        claims = event['requestContext']['authorizer']['jwt']['claims']
        tenant_id = claims['custom:tenant_id']
        
        # Parse the updates from the request body
        body = json.loads(event.get("body", "{}"))
        new_tenant_name = body.get("tenant_name")
        new_subreddits = body.get("subreddits")

        if not new_tenant_name or not isinstance(new_subreddits, list):
            return {"statusCode": 400, "body": json.dumps({"error": "tenant_name and a list of subreddits are required."})}

        print(f"Updating watchlist for tenant_id: {tenant_id}")

        # Use UpdateItem to safely update the tenant's configuration
        tenants_table.update_item(
            Key={'tenant_id': tenant_id},
            UpdateExpression="SET tenant_name = :n, subreddits = :s",
            ExpressionAttributeValues={
                ':n': new_tenant_name,
                ':s': new_subreddits
            }
        )
        
        return {
            "statusCode": 200,
            "headers": { "Access-Control-Allow-Origin": "*" },
            "body": json.dumps({"message": "Watchlist updated successfully."})
        }
        
    except Exception as e:
        print(f"Error updating watchlist: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": "Could not update watchlist."})}