#!/bin/bash
#
# EchoStream v2.0 - Post-Deployment Setup Script
#
# This script automates the manual setup tasks required after a clean
# deployment of the CloudFormation stack.
#

# Exit immediately if a command exits with a non-zero status.
set -e
# Disable the AWS CLI pager
export AWS_PAGER=""

# --- Configuration ---
STACK_NAME="echostream-prod"
# Use the region defined in the AWS CLI profile
REGION=$(aws configure get region)
TEST_USERNAME="RickSanchez"

# Check if .env file exists and source it
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Please create it with your Reddit credentials."
    exit 1
fi
source .env
echo "✅ Loaded credentials from .env file."

# --- Step 1: Fetch Stack Outputs ---
echo "--- [1/5] Fetching Stack Outputs from CloudFormation ---"
STACK_OUTPUTS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query "Stacks[0].Outputs" --output json)

USER_POOL_ID=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="UserPoolId") | .OutputValue')
CLIENT_ID=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="UserPoolClientId") | .OutputValue')
API_URL=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="HttpApiUrl") | .OutputValue')
PRODUCER_LAMBDA_NAME=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="ProducerLambdaName") | .OutputValue')
SECRET_ARN=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="RedditCredentialsSecretArn") | .OutputValue')
TENANTS_TABLE_NAME=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="TenantsTableName") | .OutputValue')

echo "  > User Pool ID: $USER_POOL_ID"
echo "  > Client ID:    $CLIENT_ID"
echo "✅ Successfully fetched stack outputs."


# --- Step 2: Update Reddit Secret in Secrets Manager ---
echo "--- [2/5] Updating Reddit Credentials in Secrets Manager ---"

# Use jq to safely build the JSON string, preventing shell expansion issues
SECRET_STRING=$(jq -n \
                  --arg client_id "$REDDIT_CLIENT_ID" \
                  --arg client_secret "$REDDIT_CLIENT_SECRET" \
                  --arg user_agent "$REDDIT_USER_AGENT" \
                  --arg username "$REDDIT_USERNAME" \
                  --arg password "$REDDIT_PASSWORD" \
                  '{
                    "REDDIT_CLIENT_ID": $client_id,
                    "REDDIT_CLIENT_SECRET": $client_secret,
                    "REDDIT_USER_AGENT": $user_agent,
                    "REDDIT_USERNAME": $username,
                    "REDDIT_PASSWORD": $password
                   }')

aws secretsmanager update-secret --secret-id $SECRET_ARN --secret-string "$SECRET_STRING" --region $REGION

# Add a short sleep to allow for propagation
echo "Secret updated. Waiting 5 seconds for propagation..."
sleep 5

echo "✅ Secret updated successfully and is now available."


# --- Step 3: Create Tenant Data in DynamoDB ---
echo "--- [3/5] Seeding TenantsTable with 5 tenants ---"
TENANTS_JSON_FILE=$(mktemp)
cat > $TENANTS_JSON_FILE << EOL
{
    "$TENANTS_TABLE_NAME": [
        {"PutRequest": {"Item": {"tenant_id": {"S": "e47c136a-2d3a-4f5b-8c9d-1e2f3a4b5c6d"}, "is_active": {"BOOL": true}, "subreddits": {"L": [{"S": "sports"}, {"S": "nba"}, {"S": "Music"}]}, "tenant_name": {"S": "Sports & Music Analytics"}}}},
        {"PutRequest": {"Item": {"tenant_id": {"S": "f58d247b-3e4b-4a6c-9d0e-2f3a4b5c6d7e"}, "is_active": {"BOOL": true}, "subreddits": {"L": [{"S": "politics"}, {"S": "worldnews"}]}, "tenant_name": {"S": "Global Affairs Monitor"}}}},
        {"PutRequest": {"Item": {"tenant_id": {"S": "a69e358c-4f5c-4b7d-8e1f-3a4b5c6d7e8f"}, "is_active": {"BOOL": true}, "subreddits": {"L": [{"S": "natureisfuckinglit"}, {"S": "aww"}]}, "tenant_name": {"S": "Nature & Wildlife Insights"}}}},
        {"PutRequest": {"Item": {"tenant_id": {"S": "b70f469d-5a6d-4c8e-9f2a-4b5c6d7e8f9a"}, "is_active": {"BOOL": true}, "subreddits": {"L": [{"S": "technology"}, {"S": "gaming"}]}, "tenant_name": {"S": "Tech & Gaming Trends"}}}},
        {"PutRequest": {"Item": {"tenant_id": {"S": "c81a570e-6b7e-4d9f-8a3b-5c6d7e8f9g0b"}, "is_active": {"BOOL": true}, "subreddits": {"L": [{"S": "stocks"}, {"S": "wallstreetbets"}]}, "tenant_name": {"S": "Financial Market Sentiments"}}}}
    ]
}
EOL
aws dynamodb batch-write-item --request-items file://$TENANTS_JSON_FILE --region $REGION
rm $TENANTS_JSON_FILE
echo "✅ 5 tenants created successfully."


# --- Step 4: Create and Configure Test User in Cognito ---
echo "--- [4/5] Creating and configuring test user '$TEST_USERNAME' ---"
# Create the user
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username $TEST_USERNAME \
  --user-attributes Name=email,Value=test@example.com Name=email_verified,Value=True \
  --message-action SUPPRESS \
  --region $REGION

# Set a permanent password for the user
aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username $TEST_USERNAME \
  --password "Password123!" \
  --permanent \
  --region $REGION

# Assign the user to the "Tech & Gaming" tenant
aws cognito-idp admin-update-user-attributes \
  --user-pool-id $USER_POOL_ID \
  --username $TEST_USERNAME \
  --user-attributes Name="custom:tenant_id",Value="b70f469d-5a6d-4c8e-9f2a-4b5c6d7e8f9a" \
  --region $REGION
echo "✅ Test user '$TEST_USERNAME' created and assigned to a tenant."


# --- Step 5: Trigger Producer Lambda to Seed Data ---
echo "--- [5/5] Invoking Producer Lambda to seed initial data ---"
aws lambda invoke --function-name $PRODUCER_LAMBDA_NAME --region $REGION /dev/null
echo "✅ Producer Lambda invoked. Data should be flowing into the pipeline."

echo "                      "
echo "--- SETUP COMPLETE ---"
echo "You can now test the query API or the frontend."