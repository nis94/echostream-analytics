# In create-tenant/app.py
import os
import json
import boto3
import uuid

cognito_client = boto3.client('cognito-idp')
dynamodb = boto3.resource('dynamodb')

TENANTS_TABLE_NAME = os.environ.get("TENANTS_TABLE_NAME")
tenants_table = dynamodb.Table(TENANTS_TABLE_NAME)

def lambda_handler(event, context):
    """
    Handles a POST request from a newly signed-up user to create their first tenant.
    """
    print(f"Received event: {event}")
    
    try:
        # Get the user's details securely from their validated token
        claims = event['requestContext']['authorizer']['jwt']['claims']
        user_pool_id = claims['iss'].split('/')[-1]
        username = claims['cognito:username']
        user_email = claims['email']

        # Get the desired tenant name from the request body
        body = json.loads(event.get("body", "{}"))
        tenant_name = body.get("tenant_name")

        if not tenant_name:
            return {"statusCode": 400, "body": json.dumps({"error": "tenant_name is required."})}

        # 1. Generate a new tenant ID
        tenant_id = str(uuid.uuid4())
        print(f"Creating new tenant {tenant_id} for user {username}")

        # 2. Create the new tenant item in DynamoDB
        tenants_table.put_item(
            Item={
                'tenant_id': tenant_id,
                'tenant_name': tenant_name,
                'is_active': True,
                'subreddits': [], # Start with an empty watchlist
                'contact_email': user_email
            }
        )

        # 3. Update the user's custom attribute with the new tenant ID
        cognito_client.admin_update_user_attributes(
            UserPoolId=user_pool_id,
            Username=username,
            UserAttributes=[{'Name': 'custom:tenant_id', 'Value': tenant_id}]
        )
        
        # 4. Add this user to the 'admins' group for the new tenant
        cognito_client.admin_add_user_to_group(
            UserPoolId=user_pool_id,
            Username=username,
            GroupName='admins'
        )

        return {
            "statusCode": 200,
            "headers": { "Access-Control-Allow-Origin": "*" },
            "body": json.dumps({"message": "Tenant created successfully", "tenant_id": tenant_id})
        }

    except Exception as e:
        print(f"Error creating tenant: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": "Could not create tenant."})}