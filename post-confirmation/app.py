import json

def lambda_handler(event, context):
    """
    This function is triggered by Cognito after a new user confirms.
    In v3.0, its primary role is simply to log the sign-up event. Tenant creation
    is now handled by a separate, user-initiated API call.
    """
    user_email = event['request']['userAttributes'].get('email')
    user_name = event['userName']
    
    print(f"New user confirmed. Username: {user_name}, Email: {user_email}")
    
    # It's required to return the original event object back to Cognito
    return event