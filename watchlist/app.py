import os
import json
import boto3

dynamodb = boto3.resource("dynamodb")
TENANTS_TABLE_NAME = os.environ.get("TENANTS_TABLE_NAME")
tenants_table = dynamodb.Table(TENANTS_TABLE_NAME)

def lambda_handler(event, context):
    """
    Handles secure POST requests to update a tenant's watchlist
    (a list of source/topic objects) and tenant_name.
    """
    print(f"Received event: {event}")
    
    try:
        claims = event['requestContext']['authorizer']['jwt']['claims']
        tenant_id = claims['custom:tenant_id']
        
        body = json.loads(event.get("body", "{}"))
        new_tenant_name = body.get("tenant_name")
        new_watchlist = body.get("watchlist") # Expecting a list of objects now

        # Basic validation for the new structure
        if not new_tenant_name or not isinstance(new_watchlist, list):
            return {"statusCode": 400, "body": json.dumps({"error": "tenant_name and a list of watchlist items are required."})}
        for item in new_watchlist:
            if not all(k in item for k in ("source", "topic")):
                return {"statusCode": 400, "body": json.dumps({"error": "Each watchlist item must contain 'source' and 'topic'."})}

        print(f"Updating watchlist for tenant_id: {tenant_id}")

        tenants_table.update_item(
            Key={'tenant_id': tenant_id},
            UpdateExpression="SET tenant_name = :n, watchlist = :w",
            ExpressionAttributeValues={
                ':n': new_tenant_name,
                ':w': new_watchlist
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