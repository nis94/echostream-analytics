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
    This function is triggered by Cognito after a new user confirms their sign-up.
    It creates a new tenant, assigns the user as the admin, and updates their
    attributes in Cognito.
    """
    print(f"Received Cognito event: {json.dumps(event)}")

    user_pool_id = event['userPoolId']
    user_name = event['userName']
    user_email = event['request']['userAttributes'].get('email')

    # 1. Generate a new, unique tenant ID
    tenant_id = str(uuid.uuid4())
    print(f"Generated new tenant_id: {tenant_id} for user: {user_name}")

    # 2. Create a new tenant item in the TenantsTable
    try:
        tenants_table.put_item(
            Item={
                'tenant_id': tenant_id,
                'tenant_name': f"{user_email}'s Team",
                'is_active': True,
                'subreddits': [], # Start with an empty watchlist
                'contact_email': user_email
            }
        )
        print(f"Successfully created new tenant item for {tenant_id}")
    except Exception as e:
        print(f"ERROR: Failed to create tenant in DynamoDB. {e}")
        # Return the event to Cognito without modification on failure
        return event

    # 3. Update the user's custom attribute with the new tenant ID
    try:
        cognito_client.admin_update_user_attributes(
            UserPoolId=user_pool_id,
            Username=user_name,
            UserAttributes=[
                {
                    'Name': 'custom:tenant_id',
                    'Value': tenant_id
                },
            ]
        )
        print(f"Successfully updated custom:tenant_id for user {user_name}")
    except Exception as e:
        print(f"ERROR: Failed to update user attributes in Cognito. {e}")
        return event
        
    # 4. Add the user to the 'admins' group
    try:
        cognito_client.admin_add_user_to_group(
            UserPoolId=user_pool_id,
            Username=user_name,
            GroupName='admins'
        )
        print(f"Successfully added user {user_name} to 'admins' group.")
    except Exception as e:
        print(f"ERROR: Failed to add user to admins group. {e}")
        return event

    # It's required to return the event object back to Cognito
    return event