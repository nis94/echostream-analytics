import os
import json
import boto3

cognito_client = boto3.client('cognito-idp')

def lambda_handler(event, context):
    """
    Handles a POST request from a tenant admin to invite a new user.
    Implements a "find or create" workflow.
    """
    print(f"Received event: {event}")
    
    try:
        # Get the admin's details securely from their validated token
        claims = event['requestContext']['authorizer']['jwt']['claims']
        admin_tenant_id = claims.get('custom:tenant_id')
        admin_groups = claims.get('cognito:groups', [])

        # Security Check: Only admins can invite users
        if 'admins' not in admin_groups:
            return {"statusCode": 403, "body": json.dumps({"error": "Forbidden: Only admins can invite users."})}

        # Get the email of the user to invite from the request body
        body = json.loads(event.get("body", "{}"))
        invitee_email = body.get("email")

        if not invitee_email:
            return {"statusCode": 400, "body": json.dumps({"error": "email is required."})}

        user_pool_id = claims['iss'].split('/')[-1]
        
        # Step 1: Find if a user with that email already exists
        response = cognito_client.list_users(
            UserPoolId=user_pool_id,
            Filter=f"email = \"{invitee_email}\""
        )
        
        username_to_add = None
        
        if response['Users']:
            # User already exists
            existing_user = response['Users'][0]
            username_to_add = existing_user['Username']
            print(f"User {invitee_email} already exists with username {username_to_add}. Adding to tenant.")
        else:
            # User does not exist, create them
            username_to_add = invitee_email # Use email as username for simplicity
            print(f"User {invitee_email} does not exist. Creating new user.")
            cognito_client.admin_create_user(
                UserPoolId=user_pool_id,
                Username=username_to_add,
                UserAttributes=[{'Name': 'email', 'Value': invitee_email}, {'Name': 'email_verified', 'Value': 'True'}],
                MessageAction='SUPPRESS' # Suppress welcome email, send custom one later if needed
            )

        # Step 2: Add the user (either found or created) to the tenant and 'members' group
        cognito_client.admin_update_user_attributes(
            UserPoolId=user_pool_id,
            Username=username_to_add,
            UserAttributes=[{'Name': 'custom:tenant_id', 'Value': admin_tenant_id}]
        )
        
        cognito_client.admin_add_user_to_group(
            UserPoolId=user_pool_id,
            Username=username_to_add,
            GroupName='members'
        )

        return {
            "statusCode": 200,
            "headers": { "Access-Control-Allow-Origin": "*" },
            "body": json.dumps({"message": f"Successfully invited user {invitee_email} to your team."})
        }

    except Exception as e:
        print(f"Error inviting user: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": "Could not process invitation."})}