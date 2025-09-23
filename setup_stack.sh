#!/bin/bash
#
#Post-Deployment Setup Script
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
echo "--- [1/5] Fetching Stack Outputs from CloudFormation ---"
STACK_OUTPUTS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query "Stacks[0].Outputs" --output json)
USER_POOL_ID=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="UserPoolId") | .OutputValue')
CLIENT_ID=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="UserPoolClientId") | .OutputValue')
PRODUCER_LAMBDA_NAME=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="ProducerLambdaName") | .OutputValue')
SECRET_ARN=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="RedditCredentialsSecretArn") | .OutputValue')
TENANTS_TABLE_NAME=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="TenantsTableName") | .OutputValue')
echo "✅ Successfully fetched stack outputs."


# --- Step 2: Update Reddit Secret in Secrets Manager ---
echo "--- [2/5] Updating Reddit Credentials in Secrets Manager ---"
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
echo "✅ Secret updated successfully and is now available."


# --- Step 3: Create Tenant Data in DynamoDB ---
echo "--- [3/5] Seeding TenantsTable with 2 new tenants ---"
TENANTS_JSON_FILE=$(mktemp)
# Define the tenant data using variables from our .env file
cat > $TENANTS_JSON_FILE << EOL
{
    "$TENANTS_TABLE_NAME": [
        {
            "PutRequest": {
                "Item": {
                    "tenant_id": {"S": "8a1b2c3d-4e5f-4a6b-8c9d-1e2f3a4b5c6d"},
                    "is_active": {"BOOL": true},
                    "subreddits": {"L": [{"S": "poker"}, {"S": "wsop"}, {"S": "ept"}, {"S": "pokerGO"}]},
                    "tenant_name": {"S": "Poker & Gaming Analytics"},
                    "contact_email": {"S": "$CONTACT_EMAIL"}
                }
            }
        },
        {
            "PutRequest": {
                "Item": {
                    "tenant_id": {"S": "9b2c3d4e-5f6a-4b7c-9d0e-2f3a4b5c6d7e"},
                    "is_active": {"BOOL": true},
                    "subreddits": {"L": [{"S": "GOOG"}, {"S": "NVDA"}, {"S": "AAPL"}, {"S": "MSFT"}]},
                    "tenant_name": {"S": "Blue Chip Stock Monitor"},
                    "contact_email": {"S": "$CONTACT_EMAIL"}
                }
            }
        }
    ]
}
EOL
aws dynamodb batch-write-item --request-items file://$TENANTS_JSON_FILE --region $REGION
rm $TENANTS_JSON_FILE
echo "✅ 2 new tenants created successfully."


# --- Step 4: Create and Configure Test User in Cognito ---
echo "--- [4/5] Creating and configuring test user '$TEST_USERNAME' ---"
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

# Assign the user to the "Blue Chip Stocks" tenant
aws cognito-idp admin-update-user-attributes \
  --user-pool-id $USER_POOL_ID \
  --username $TEST_USERNAME \
  --user-attributes Name="custom:tenant_id",Value="9b2c3d4e-5f6a-4b7c-9d0e-2f3a4b5c6d7e" \
  --region $REGION
echo "✅ Test user '$TEST_USERNAME' created and assigned to the stocks tenant."


# --- Step 5: Trigger Producer Lambda to Seed Data ---
echo "--- [5/5] Invoking Producer Lambda to seed initial data ---"
aws lambda invoke --function-name $PRODUCER_LAMBDA_NAME --region $REGION /dev/null
echo "✅ Producer Lambda invoked. Data should be flowing into the pipeline."

echo "\n--- SETUP COMPLETE ---"