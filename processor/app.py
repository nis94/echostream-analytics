import os
import json
import boto3
from datetime import datetime
from decimal import Decimal

# --- AWS Clients ---
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
comprehend = boto3.client("comprehend")
DATA_LAKE_BUCKET = os.environ.get("DATA_LAKE_BUCKET")
DATA_TABLE_NAME = os.environ.get("DATA_TABLE")
table = dynamodb.Table(DATA_TABLE_NAME)

# --- Pluggable Sentiment Analysis Engine (with lazy imports) ---
class ComprehendSentimentAnalyzer:
    def detect_sentiment(self, text):
        truncated_text = text.encode('utf-8')[:5000].decode('utf-8', 'ignore')
        print(f"Calling Comprehend for text: {truncated_text[:100]}...")
        return comprehend.detect_sentiment(Text=truncated_text, LanguageCode="en")

ANALYZERS = {"comprehend": ComprehendSentimentAnalyzer}

def get_analyzer(engine_name="comprehend"):
    AnalyzerClass = ANALYZERS.get(engine_name)
    if not AnalyzerClass:
        raise ValueError(f"Unknown sentiment engine: {engine_name}")
    return AnalyzerClass()

# --- Main Lambda Handler (Refactored for SQS) ---
def lambda_handler(event, context):
    """
    Receives a batch of messages from SQS, enriches them with sentiment analysis,
    and stores them in S3 and DynamoDB.
    """
    print(f"Received SQS event with {len(event.get('Records', []))} messages.")
    
    engine_name = os.environ.get("SENTIMENT_ENGINE", "comprehend")
    analyzer = get_analyzer(engine_name)
    
    items_to_write = []
    
    # --- NEW: SQS EVENT PARSING LOGIC ---
    for record in event.get('Records', []):
        try:
            # The message from the producer is in the 'body' of the SQS record
            payload = json.loads(record['body'])
            
            tenant_id = payload['tenant_id']
            topic = payload['topic']
            post = payload['post']
            
            # 1. Write the raw payload to S3
            now = datetime.utcnow()
            s3_key = f"raw/{tenant_id}/{topic}/{now.strftime('%Y/%m/%d')}/{post['id']}.json"
            s3.put_object(Bucket=DATA_LAKE_BUCKET, Key=s3_key, Body=json.dumps(payload))
            
            # 2. Enrich the post with sentiment
            sentiment_result = analyzer.detect_sentiment(post["text"])
            
            # 3. Prepare the enriched item for DynamoDB
            item = {
                "PK": f"{tenant_id}#{topic}",
                "SK": f"{post['timestamp']}#{post['id']}",
                "id": post["id"],
                "text": post["text"],
                "author": post["author"],
                "timestamp": post["timestamp"],
                "source": post["source"],
                "sentiment": sentiment_result.get("Sentiment"),
                "sentiment_score_positive": str(Decimal(str(sentiment_result.get("SentimentScore", {}).get("Positive", 0)))),
                "sentiment_score_negative": str(Decimal(str(sentiment_result.get("SentimentScore", {}).get("Negative", 0)))),
                "sentiment_score_neutral": str(Decimal(str(sentiment_result.get("SentimentScore", {}).get("Neutral", 0)))),
                "sentiment_score_mixed": str(Decimal(str(sentiment_result.get("SentimentScore", {}).get("Mixed", 0)))),
            }
            items_to_write.append(item)

        except Exception as e:
            print(f"Could not process record. Skipping. Error: {e}")
            continue

    if not items_to_write:
        print("No processable items found in the event. Exiting.")
        return

    # 4. Write the batch of enriched items to DynamoDB
    try:
        with table.batch_writer() as batch:
            for item in items_to_write:
                batch.put_item(Item=item)
        print(f"Successfully processed and stored {len(items_to_write)} posts.")
    except Exception as e:
        print(f"Error during DynamoDB batch write: {e}")
        raise e

    return {
        "statusCode": 200,
        "body": "Successfully processed records."
    }