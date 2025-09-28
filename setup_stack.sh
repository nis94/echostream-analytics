#!/bin/bash
#
# EchoStream v4.0 - Post-Deployment Setup Script
#
# This script automates the initial backend configuration for secrets
# and creates a pre-configured admin user for testing.
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
    echo "ERROR: .env file not found. Please create it with your credentials."
    exit 1
fi
source .env
echo "✅ Loaded credentials from .env file."

# --- Step 1: Fetch Stack Outputs ---
echo "--- [1/4] Fetching Stack Outputs from CloudFormation ---"
STACK_OUTPUTS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query "Stacks[0].Outputs" --output json)
USER_POOL_ID=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="UserPoolId") | .OutputValue')
CLIENT_ID=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="UserPoolClientId") | .OutputValue')
REDDIT_SECRET_ARN=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="RedditCredentialsSecretArn") | .OutputValue')
NEWS_SECRET_ARN=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="NewsApiSecretArn") | .OutputValue')
echo "✅ Successfully fetched stack outputs."


# --- Step 2: Update Reddit Secret in Secrets Manager ---
echo "--- [2/4] Updating Reddit Credentials in Secrets Manager ---"
SECRET_STRING=$(python3 -c '
import os, json
# Keys must be UPPERCASE to match the Python app''s expectations
credentials = {
    "REDDIT_CLIENT_ID": os.environ["REDDIT_CLIENT_ID"],
    "REDDIT_CLIENT_SECRET": os.environ["REDDIT_CLIENT_SECRET"],
    "REDDIT_USER_AGENT": os.environ["REDDIT_USER_AGENT"],
    "REDDIT_USERNAME": os.environ["REDDIT_USERNAME"],
    "REDDIT_PASSWORD": os.environ["REDDIT_PASSWORD"]
}
print(json.dumps(credentials))
')
aws secretsmanager update-secret --secret-id $REDDIT_SECRET_ARN --secret-string "$SECRET_STRING" --region $REGION
echo "✅ Reddit secret updated successfully."


# --- Step 3: Update NewsAPI Key in Secrets Manager ---
echo "--- [3/4] Updating NewsAPI Key in Secrets Manager ---"
NEWS_SECRET_STRING=$(python3 -c '
import os, json
secret_data = {"NEWS_API_KEY": os.environ["NEWS_API_KEY"]}
print(json.dumps(secret_data))
')
aws secretsmanager update-secret --secret-id $NEWS_SECRET_ARN --secret-string "$NEWS_SECRET_STRING" --region $REGION
echo "Secret updated. Waiting 5 seconds for propagation..."
sleep 5
echo "✅ NewsAPI secret updated successfully."


# --- Step 4: Create an Initial Admin User in Cognito ---
echo "--- [4/4] Creating initial admin user '$TEST_USERNAME' ---"
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
echo "✅ Admin user '$TEST_USERNAME' created. You can use this user for testing or sign up a new one."


echo "\n--- SETUP COMPLETE ---"
echo "The backend is configured. You can now use the frontend to sign up new users."