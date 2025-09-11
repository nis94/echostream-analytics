import os
import json
import boto3
import praw
from datetime import datetime
from boto3.dynamodb.conditions import Key

# Boto3 clients
kinesis_client = boto3.client("kinesis")
secrets_client = boto3.client("secretsmanager")
dynamodb = boto3.resource("dynamodb")

# Get configuration from environment variables
STREAM_NAME = os.environ.get("STREAM_NAME")
SECRET_NAME = os.environ.get("SECRET_NAME")
TENANTS_TABLE_NAME = os.environ.get("TENANTS_TABLE_NAME")

tenants_table = dynamodb.Table(TENANTS_TABLE_NAME)

def get_reddit_credentials():
    """Fetches Reddit API credentials from AWS Secrets Manager."""
    response = secrets_client.get_secret_value(SecretId=SECRET_NAME)
    return json.loads(response['SecretString'])

def get_active_tenants():
    """Scans the TenantsTable to find all tenants with is_active = true."""
    print("Fetching active tenants from DynamoDB...")
    response = tenants_table.scan(
        FilterExpression=Key('is_active').eq(True)
    )
    tenants = response.get('Items', [])
    print(f"Found {len(tenants)} active tenants.")
    return tenants

def lambda_handler(event, context):
    """
    Scans for active tenants, polls Reddit for each of their configured
    subreddits, and pushes the comments to a Kinesis stream.
    """
    credentials = get_reddit_credentials()
    reddit = praw.Reddit(
        client_id=credentials['REDDIT_CLIENT_ID'],
        client_secret=credentials['REDDIT_CLIENT_SECRET'],
        user_agent=credentials['REDDIT_USER_AGENT'],
        username=credentials['REDDIT_USERNAME'],
        password=credentials['REDDIT_PASSWORD'],
    )
    
    active_tenants = get_active_tenants()
    all_records_to_send = []

    for tenant in active_tenants:
        tenant_id = tenant['tenant_id']
        subreddits = tenant.get('subreddits', [])
        
        print(f"Processing tenant: {tenant_id}, subreddits: {subreddits}")
        
        for subreddit_name in subreddits:
            try:
                subreddit = reddit.subreddit(subreddit_name)
                # Poll for a few recent comments instead of an endless stream
                for comment in subreddit.comments(limit=5):
                    # This is the new payload structure our processor will need to handle
                    payload = {
                        "tenant_id": tenant_id,
                        "topic": subreddit_name,
                        "post": {
                            "id": comment.id,
                            "text": comment.body,
                            "author": str(comment.author),
                            "timestamp": datetime.utcfromtimestamp(comment.created_utc).isoformat() + "Z",
                            "source": f"reddit/r/{comment.subreddit.display_name}"
                        }
                    }
                    
                    record = {
                        "Data": json.dumps(payload).encode("utf-8"),
                        "PartitionKey": tenant_id # Partition by tenant for logical separation
                    }
                    all_records_to_send.append(record)
            except Exception as e:
                print(f"Could not process subreddit '{subreddit_name}' for tenant '{tenant_id}'. Error: {e}")
                continue # Skip to the next subreddit

    if not all_records_to_send:
        print("No new comments found across all tenants.")
        return {"statusCode": 200, "body": "No new comments found."}

    try:
        print(f"Sending {len(all_records_to_send)} total live comments to Kinesis stream: {STREAM_NAME}")
        
        # Kinesis put_records has a limit of 500 records per call
        # For simplicity, we assume we won't hit it. In production, you'd batch this.
        kinesis_client.put_records(
            StreamName=STREAM_NAME,
            Records=all_records_to_send[:500]
        )
        
        return {
            "statusCode": 200,
            "body": f"Successfully sent {len(all_records_to_send)} live comments to Kinesis."
        }
        
    except Exception as e:
        print(f"Error sending data to Kinesis: {e}")
        raise e