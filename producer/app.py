import os
import json
import boto3
import praw
from datetime import datetime

# Boto3 clients
sqs_client = boto3.client("sqs")
secrets_client = boto3.client("secretsmanager")
dynamodb = boto3.resource("dynamodb")

# Get configuration from environment variables
QUEUE_URL = os.environ.get("QUEUE_URL")
SECRET_NAME = os.environ.get("SECRET_NAME")
TENANTS_TABLE_NAME = os.environ.get("TENANTS_TABLE_NAME")
tenants_table = dynamodb.Table(TENANTS_TABLE_NAME)

# --- Helper Functions (unchanged) ---
def get_reddit_credentials():
    """Fetches Reddit API credentials from AWS Secrets Manager."""
    response = secrets_client.get_secret_value(SecretId=SECRET_NAME)
    return json.loads(response['SecretString'])

def get_active_tenants():
    """Scans the TenantsTable to find all tenants with is_active = true."""
    print("Fetching active tenants from DynamoDB...")
    response = tenants_table.scan(FilterExpression=boto3.dynamodb.conditions.Key('is_active').eq(True))
    tenants = response.get('Items', [])
    print(f"Found {len(tenants)} active tenants.")
    return tenants

# --- Main Lambda Handler (Refactored for SQS) ---
def lambda_handler(event, context):
    """
    Scans for active tenants, polls Reddit, and sends messages to an SQS queue.
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
    messages_to_send = []

    for tenant in active_tenants:
        tenant_id = tenant['tenant_id']
        subreddits = tenant.get('subreddits', [])
        
        print(f"Processing tenant: {tenant_id}, subreddits: {subreddits}")
        
        for subreddit_name in subreddits:
            try:
                subreddit = reddit.subreddit(subreddit_name)
                for comment in subreddit.comments(limit=5):
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
                    
                    # SQS SendMessageBatch requires a list of entries
                    entry = {
                        'Id': comment.id,
                        'MessageBody': json.dumps(payload)
                    }
                    messages_to_send.append(entry)
            except Exception as e:
                print(f"Could not process subreddit '{subreddit_name}'. Error: {e}")
                continue

    if not messages_to_send:
        print("No new comments found across all tenants.")
        return {"statusCode": 200, "body": "No new comments found."}

    try:
        # SQS has a limit of 10 messages per batch call
        for i in range(0, len(messages_to_send), 10):
            batch = messages_to_send[i:i + 10]
            print(f"Sending batch of {len(batch)} messages to SQS queue: {QUEUE_URL}")
            sqs_client.send_message_batch(
                QueueUrl=QUEUE_URL,
                Entries=batch
            )
        
        return {
            "statusCode": 200,
            "body": f"Successfully sent {len(messages_to_send)} messages to SQS."
        }
    except Exception as e:
        print(f"Error sending data to SQS: {e}")
        raise e