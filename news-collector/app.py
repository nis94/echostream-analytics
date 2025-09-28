import os
import json
import boto3
import requests # We'll need to package this library with our function
from datetime import datetime, timedelta

# Boto3 clients
sqs_client = boto3.client("sqs")
secrets_client = boto3.client("secretsmanager")

QUEUE_URL = os.environ.get("QUEUE_URL")
SECRET_NAME = os.environ.get("SECRET_NAME")

def get_news_api_key():
    response = secrets_client.get_secret_value(SecretId=SECRET_NAME)
    return json.loads(response['SecretString'])['NEWS_API_KEY']

def lambda_handler(event, context):
    """
    Receives a "collection job" from SNS, polls a News API for that job,
    and pushes the articles to the SQS queue.
    """
    print(f"Received SNS event: {event}")
    api_key = get_news_api_key()
    
    messages_to_send = []

    for record in event['Records']:
        job = json.loads(record['Sns']['Message'])
        tenant_id = job['tenant_id']
        topic = job['topic']
        source = job['source']

        if source != 'news':
            continue

        print(f"Processing job for tenant: {tenant_id}, keyword: {topic}")
        try:
            # Fetch articles from the last day
            from_date = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
            url = f"https://newsapi.org/v2/everything?q={topic}&from={from_date}&sortBy=popularity&apiKey={api_key}"
            response = requests.get(url)
            response.raise_for_status()
            articles = response.json().get('articles', [])

            for article in articles[:10]: # Process the top 10 articles
                payload = {
                    "tenant_id": tenant_id, "topic": topic,
                    "post": {
                        "id": article.get('url'), # Use URL as a unique ID
                        "text": article.get('description') or article.get('content') or "",
                        "author": article.get('source', {}).get('name'),
                        "timestamp": article.get('publishedAt'),
                        "source": f"news/{article.get('source', {}).get('name')}"
                    }
                }
                messages_to_send.append({'Id': str(hash(article.get('url'))), 'MessageBody': json.dumps(payload)})
        except Exception as e:
            print(f"Could not process news topic '{topic}'. Error: {e}")

    if not messages_to_send:
        return {"statusCode": 200, "body": "No new articles found."}

    try:
        for i in range(0, len(messages_to_send), 10):
            batch = messages_to_send[i:i+10]
            print(f"Sending batch of {len(batch)} news articles to SQS.")
            sqs_client.send_message_batch(QueueUrl=QUEUE_URL, Entries=batch)
        return {"statusCode": 200, "body": f"Successfully sent {len(messages_to_send)} articles."}
    except Exception as e:
        print(f"Error sending data to SQS: {e}")
        raise e