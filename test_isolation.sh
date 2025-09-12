#!/bin/bash
#
# EchoStream v2.0 - Tenant Isolation Test Script
#
# This script logs in as a specific user and verifies that the /query API
# correctly enforces data isolation between tenants.
#

# Exit immediately if a command exits with a non-zero status.
set -e
export AWS_PAGER=""

# --- Configuration ---
STACK_NAME="echostream-prod"
REGION=$(aws configure get region)
USERNAME="RickSanchez"
PASSWORD="Password123!" # The password you set in the setup script

# Define the user's ACTUAL tenant and a topic that BELONGS to them
EXPECTED_TENANT_ID="b70f469d-5a6d-4c8e-9f2a-4b5c6d7e8f9a" # Tech & Gaming
TOPIC_IN_TENANT="gaming" # A topic that belongs to the Tech & Gaming tenant

# Define a topic that DOES NOT BELONG to the user's tenant (for the negative test)
TOPIC_OUTSIDE_TENANT="sports" # Belongs to the Sports & Music tenant

# --- Step 1: Fetch Stack Outputs ---
echo "--- [1/4] Fetching Stack Outputs from CloudFormation ---"
STACK_OUTPUTS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query "Stacks[0].Outputs" --output json)
USER_POOL_ID=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="UserPoolId") | .OutputValue')
CLIENT_ID=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="UserPoolClientId") | .OutputValue')
API_URL=$(echo $STACK_OUTPUTS | jq -r '.[] | select(.OutputKey=="HttpApiUrl") | .OutputValue')
echo "✅ Done."

# --- Step 2: Authenticate as RickSanchez ---
echo "--- [2/4] Authenticating as $USERNAME ---"
AUTH_RESULT=$(aws cognito-idp admin-initiate-auth \
  --user-pool-id $USER_POOL_ID \
  --client-id $CLIENT_ID \
  --auth-flow ADMIN_USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=$USERNAME,PASSWORD=$PASSWORD \
  --region $REGION)

ID_TOKEN=$(echo $AUTH_RESULT | jq -r '.AuthenticationResult.IdToken')

if [ -z "$ID_TOKEN" ]; then
    echo "❌ ERROR: Authentication failed. Could not get IdToken."
    exit 1
fi
echo "✅ Authentication successful."

# --- Step 3: Positive Test (Should see data) ---
echo "--- [3/4] Performing Positive Test for topic '$TOPIC_IN_TENANT' ---"
POSITIVE_RESPONSE=$(curl --silent -H "Authorization: $ID_TOKEN" "$API_URL/query?topic=$TOPIC_IN_TENANT")

# Check if the query returned any items
ITEM_COUNT=$(echo $POSITIVE_RESPONSE | jq '. | length')
if [ "$ITEM_COUNT" -gt 0 ]; then
    echo "  > SUCCESS: API returned $ITEM_COUNT item(s)."
    
    # Check if the PK of the first item matches the user's tenant ID
    FIRST_PK=$(echo $POSITIVE_RESPONSE | jq -r '.[0].PK')
    if [[ "$FIRST_PK" == "$EXPECTED_TENANT_ID#$TOPIC_IN_TENANT" ]]; then
        echo "  > ✅ Data isolation PASSED: Returned data belongs to the correct tenant."
    else
        echo "  > ❌ Data isolation FAILED: Returned PK '$FIRST_PK' does not match expected tenant '$EXPECTED_TENANT_ID'."
        exit 1
    fi
else
    echo "  > ❌ FAILED: API returned no items. (Have you run the producer to seed data?)"
    exit 1
fi

# --- Step 4: Negative Test (Should NOT see data) ---
echo "--- [4/4] Performing Negative Test for topic '$TOPIC_OUTSIDE_TENANT' ---"
NEGATIVE_RESPONSE=$(curl --silent -H "Authorization: $ID_TOKEN" "$API_URL/query?topic=$TOPIC_OUTSIDE_TENANT")

# Check if the query returned an empty array
ITEM_COUNT=$(echo $NEGATIVE_RESPONSE | jq '. | length')
if [ "$ITEM_COUNT" -eq 0 ]; then
    echo "  > ✅ Data isolation PASSED: API returned an empty array as expected."
else
    echo "  > ❌ Data isolation FAILED: API returned data from another tenant."
    exit 1
fi

echo -e "\n----------------------------------------"
echo "✅✅✅ Tenant Isolation Test Passed! ✅✅✅"
echo "----------------------------------------"