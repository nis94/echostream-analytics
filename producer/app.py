import os
import json
import boto3
import praw # New import
import uuid

# Boto3 clients
kinesis_client = boto3.client("kinesis")
secrets_client = boto3.client("secretsmanager")

# Get configuration from environment variables
STREAM_NAME = os.environ.get("STREAM_NAME")
SECRET_NAME = os.environ.get("SECRET_NAME")

# --- Function to fetch secrets ---
def get_reddit_credentials():
    """Fetches Reddit API credentials from AWS Secrets Manager."""
    response = secrets_client.get_secret_value(SecretId=SECRET_NAME)
    return json.loads(response['SecretString'])

# --- Main Lambda Handler ---
def lambda_handler(event, context):
    """
    Fetches live comments from Reddit and pushes them to a Kinesis stream.
    """
    credentials = get_reddit_credentials()
    
    # Initialize the Reddit client
    reddit = praw.Reddit(
        client_id=credentials['REDDIT_CLIENT_ID'],
        client_secret=credentials['REDDIT_CLIENT_SECRET'],
        user_agent=credentials['REDDIT_USER_AGENT'],
        username=credentials['REDDIT_USERNAME'],
        password=credentials['REDDIT_PASSWORD'],
    )
    
    subreddit = reddit.subreddit("all") # Monitor the 'all' subreddit for high volume
    print("Successfully connected to Reddit. Starting to stream comments...")
    
    records_to_send = []
    # Stream comments and limit to 10 to keep the Lambda execution short
    for comment in subreddit.stream.comments(skip_existing=True):
        post = {
            "id": comment.id,
            "text": comment.body,
            "author": str(comment.author),
            "timestamp": datetime.utcfromtimestamp(comment.created_utc).isoformat() + "Z",
            "source": f"reddit/r/{comment.subreddit.display_name}"
        }
        
        record = {
            "Data": json.dumps(post).encode("utf-8"),
            "PartitionKey": comment.id
        }
        records_to_send.append(record)
        
        # Send records in batches of 10 and then exit to avoid long runs
        if len(records_to_send) >= 10:
            break
            
    if not records_to_send:
        print("No new comments found in this invocation.")
        return {"statusCode": 200, "body": "No new comments found."}

    try:
        print(f"Sending {len(records_to_send)} live comments to Kinesis stream: {STREAM_NAME}")
        
        kinesis_client.put_records(
            StreamName=STREAM_NAME,
            Records=records_to_send
        )
        
        return {
            "statusCode": 200,
            "body": f"Successfully sent {len(records_to_send)} live comments to Kinesis."
        }
        
    except Exception as e:
        print(f"Error sending data to Kinesis: {e}")
        raise e