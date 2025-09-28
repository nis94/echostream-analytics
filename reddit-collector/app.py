# In reddit-collector/app.py
import os
import json
import boto3
import praw
from datetime import datetime

# Boto3 clients
sqs_client = boto3.client("sqs")
secrets_client = boto3.client("secretsmanager")

QUEUE_URL = os.environ.get("QUEUE_URL")
SECRET_NAME = os.environ.get("SECRET_NAME")

def get_reddit_credentials():
    response = secrets_client.get_secret_value(SecretId=SECRET_NAME)
    return json.loads(response['SecretString'])

def lambda_handler(event, context):
    """
    Receives a "collection job" from SNS, polls Reddit for that specific job,
    and pushes the comments to the SQS queue.
    """
    print(f"Received SNS event: {event}")
    credentials = get_reddit_credentials()
    
    reddit = praw.Reddit(
        client_id=credentials['REDDIT_CLIENT_ID'],
        client_secret=credentials['REDDIT_CLIENT_SECRET'],
        user_agent=credentials['REDDIT_USER_AGENT'],
        username=credentials['REDDIT_USERNAME'],
        password=credentials['REDDIT_PASSWORD']
    )
    
    messages_to_send = []

    for record in event['Records']:
        job = json.loads(record['Sns']['Message'])
        tenant_id = job['tenant_id']
        topic = job['topic']
        source = job['source']

        # This collector only handles 'reddit' jobs
        if source != 'reddit':
            continue

        print(f"Processing job for tenant: {tenant_id}, subreddit: {topic}")
        try:
            subreddit = reddit.subreddit(topic)
            for comment in subreddit.comments(limit=10): # Fetch 10 comments per run
                payload = {
                    "tenant_id": tenant_id, "topic": topic,
                    "post": {
                        "id": comment.id, "text": comment.body, "author": str(comment.author),
                        "timestamp": datetime.utcfromtimestamp(comment.created_utc).isoformat() + "Z",
                        "source": f"reddit/r/{comment.subreddit.display_name}"
                    }
                }
                messages_to_send.append({'Id': comment.id, 'MessageBody': json.dumps(payload)})
        except Exception as e:
            print(f"Could not process subreddit '{topic}'. Error: {e}")

    if not messages_to_send:
        print("No new comments found for the processed jobs.")
        return {"statusCode": 200, "body": "No new comments found."}

    try:
        for i in range(0, len(messages_to_send), 10):
            batch = messages_to_send[i:i+10]
            print(f"Sending batch of {len(batch)} messages to SQS.")
            sqs_client.send_message_batch(QueueUrl=QUEUE_URL, Entries=batch)
        return {"statusCode": 200, "body": f"Successfully sent {len(messages_to_send)} messages."}
    except Exception as e:
        print(f"Error sending data to SQS: {e}")
        raise e