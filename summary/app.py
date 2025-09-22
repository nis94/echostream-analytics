# In summary/app.py
import os
import json
import boto3
from decimal import Decimal

dynamodb = boto3.resource("dynamodb")
TENANTS_TABLE_NAME = os.environ.get("TENANTS_TABLE_NAME")
tenants_table = dynamodb.Table(TENANTS_TABLE_NAME)

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    """
    Handles secure requests to get the logged-in tenant's latest AI summary.
    """
    print(f"Received event: {event}")
    
    try:
        claims = event['requestContext']['authorizer']['jwt']['claims']
        tenant_id = claims['custom:tenant_id']
        
        print(f"Fetching summary for tenant_id: {tenant_id}")
        
        response = tenants_table.get_item(Key={'tenant_id': tenant_id})
        
        item = response.get("Item")
        if not item:
            return {"statusCode": 404, "body": json.dumps({"error": "Tenant configuration not found."})}
        
        summary_data = {
            "summary": item.get("latest_summary", "No summary available yet."),
            "updated_at": item.get("summary_updated_at", "N/A")
        }
        
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,Authorization",
                "Access-Control-Allow-Methods": "GET,OPTIONS"
            },
            "body": json.dumps(summary_data, cls=DecimalEncoder)
        }
        
    except Exception as e:
        print(f"Error fetching summary: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": "Could not retrieve tenant summary."})}