# In config/app.py
import os
import json
import boto3
from decimal import Decimal

dynamodb = boto3.resource("dynamodb")
TENANTS_TABLE_NAME = os.environ.get("TENANTS_TABLE_NAME")
tenants_table = dynamodb.Table(TENANTS_TABLE_NAME)

# Helper to handle DynamoDB's Decimal type in JSON
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    """
    Handles secure requests to get the logged-in tenant's configuration.
    """
    print(f"Received event: {event}")
    
    try:
        claims = event['requestContext']['authorizer']['jwt']['claims']
        tenant_id = claims['custom:tenant_id']
        
        print(f"Fetching config for tenant_id: {tenant_id}")
        
        # Use GetItem for a highly efficient lookup
        response = tenants_table.get_item(Key={'tenant_id': tenant_id})
        
        item = response.get("Item")
        if not item:
            return {"statusCode": 404, "body": json.dumps({"error": "Tenant configuration not found."})}
        
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,Authorization",
                "Access-Control-Allow-Methods": "GET,OPTIONS"
            },
            "body": json.dumps(item, cls=DecimalEncoder)
        }
        
    except KeyError:
        return {"statusCode": 400, "body": json.dumps({"error": "Tenant ID not found in user token."})}
    except Exception as e:
        print(f"Error fetching config: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": "Could not retrieve tenant configuration."})}