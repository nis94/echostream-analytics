#!/bin/bash
#
# EchoStream v2.0 - Stack Cleanup Script
# This script automates emptying S3 buckets and deleting the stack.
#

# Exit immediately if a command exits with a non-zero status.
set -e
export AWS_PAGER=""

STACK_NAME="echostream-prod"
REGION=$(aws configure get region || echo "us-east-1") # Fallback to us-east-1 if not configured

echo "--- Starting cleanup for stack: $STACK_NAME in region: $REGION ---"

# Step 1: Find the S3 buckets from the stack resources
echo "[1/3] Finding S3 buckets in the stack..."
# The '|| true' prevents the script from exiting if the stack doesn't exist
RESOURCES=$(aws cloudformation list-stack-resources --stack-name $STACK_NAME --region $REGION --query "StackResourceSummaries[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" --output text || true)

if [ -z "$RESOURCES" ]; then
    echo "  > No S3 buckets found, or stack does not exist."
else
    # Step 2: Force-empty each bucket
    echo "[2/3] Emptying S3 buckets..."
    for BUCKET in $RESOURCES; do
        echo "  > Emptying bucket: $BUCKET"
        # The 's3 rm' with '--recursive' deletes all objects and prefixes.
        # The '|| true' at the end ensures the script doesn't fail if the bucket is already empty.
        aws s3 rm s3://$BUCKET --recursive --region $REGION || true
    done
    echo "✅ Buckets emptied."
fi

# Step 3: Delete the CloudFormation stack
echo "[3/3] Deleting the CloudFormation stack..."
aws cloudformation delete-stack --stack-name $STACK_NAME --region $REGION
echo "  > Deletion command issued. Waiting for stack to be deleted..."

aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME --region $REGION
echo "✅ Stack '$STACK_NAME' has been successfully deleted."

echo "\n--- CLEANUP COMPLETE ---"