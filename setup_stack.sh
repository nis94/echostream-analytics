#!/bin/bash
#
# EchoStream v2.0 - Post-Deployment Setup Script (Streamlined)
#
# This script automates the initial backend configuration. It no longer
# creates tenants or seeds data, as this is now handled by the
# self-service sign-up and the automated producer schedule.
#

# Exit immediately if a command exits with a non-zero status.
set -e
export AWS_PAGER=""

# --- Configuration ---
STACK_NAME="echostream-prod"
REGION=$(aws configure get region || echo "us-east-1")
TEST_USERNAME="RickSanchez"

# Check if .env file exists and source it
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Please create it with your Reddit credentials."
    exit 1
fi
source .env
echo "✅ Loaded credentials from .env file."

# --- Step 1: Fetch Stack Outputs ---
echo "--- [1/3] Fetching Stack Outputs from CloudFormation ---"
STACK_OUTPUTS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query "Stacks[0].Outputs" --output json)
USER_POOL_ID=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="UserPoolId") | .OutputValue')
CLIENT_ID=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="UserPoolClientId") | .OutputValue')
SECRET_ARN=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="RedditCredentialsSecretArn") | .OutputValue')
echo "✅ Successfully fetched stack outputs."


# --- Step 2: Update Reddit Secret in Secrets Manager ---
echo "--- [2/3] Updating Reddit Credentials in Secrets Manager ---"
SECRET_JSON_FILE=$(mktemp)
cat > $SECRET_JSON_FILE << EOL
{
    "REDDIT_CLIENT_ID": "$REDDIT_CLIENT_ID",
    "REDDIT_CLIENT_SECRET": "$REDDIT_CLIENT_SECRET",
    "REDDIT_USER_AGENT": "$REDDIT_USER_AGENT",
    "REDDIT_USERNAME": "$REDDIT_USERNAME",
    "REDDIT_PASSWORD": "$REDDIT_PASSWORD"
}
EOL
aws secretsmanager update-secret --secret-id $SECRET_ARN --secret-string file://$SECRET_JSON_FILE --region $REGION
rm $SECRET_JSON_FILE
echo "Secret updated. Waiting 5 seconds for propagation..."
sleep 5
echo "✅ Secret updated successfully."


# --- Step 3: Create an Initial Admin User in Cognito ---
echo "--- [3/3] Creating initial admin user '$TEST_USERNAME' ---"
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username $TEST_USERNAME \
  --user-attributes Name=email,Value=$CONTACT_EMAIL Name=email_verified,Value=True \
  --message-action SUPPRESS \
  --region $REGION

aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username $TEST_USERNAME \
  --password "Password123!" \
  --permanent \
  --region $REGION

# We create the user but do NOT assign a tenant_id. This is a super-admin.
# Or, we can assign them to a pre-defined admin tenant. For now, we leave them unassigned.
echo "✅ Admin user '$TEST_USERNAME' created. You can use this user for testing."


echo "\n--- SETUP COMPLETE ---"
echo "The backend is configured. You can now use the frontend to sign up new users."