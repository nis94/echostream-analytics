import os
import json
import boto3 # Make sure boto3 is imported
import uuid
from datetime import datetime

# --- AWS Clients ---
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
comprehend = boto3.client("comprehend") # Add the Comprehend client
DATA_LAKE_BUCKET = os.environ.get("DATA_LAKE_BUCKET")
DATA_TABLE = os.environ.get("DATA_TABLE")
table = dynamodb.Table(DATA_TABLE)

# --- Pluggable Sentiment Analysis Engine ---

class ComprehendSentimentAnalyzer:
    """Uses AWS Comprehend to detect sentiment."""
    def detect_sentiment(self, text):
        # The DetectSentiment API has a 5000 byte limit on text size
        # We truncate the text to ensure we don't exceed this limit.
        truncated_text = text.encode('utf-8')[:5000].decode('utf-8', 'ignore')
        
        print(f"Calling Comprehend for text: {truncated_text[:100]}...")
        
        # This is the actual API call to AWS Comprehend 
        response = comprehend.detect_sentiment(
            Text=truncated_text,
            LanguageCode="en"
        )
        # The response format is already what we need, so we just return it.
        # e.g., {'Sentiment': 'POSITIVE', 'SentimentScore': {...}}
        return response

# ... (The rest of your processor/app.py file remains the same) ...

class NLTKSentimentAnalyzer:
    """Uses a self-hosted NLTK model to detect sentiment."""
    def detect_sentiment(self, text):
        # TODO: Implement self-hosted NLTK VADER logic in a future step
        print("Pretending to run NLTK model...")
        return {"Sentiment": "NEUTRAL", "SentimentScore": {"Neutral": 0.99}}

# A simple factory to select our analyzer
ANALYZERS = {
    "comprehend": ComprehendSentimentAnalyzer,
    "nltk": NLTKSentimentAnalyzer
}

def get_analyzer(engine_name="comprehend"):
    """Returns an instance of the requested sentiment analyzer."""
    AnalyzerClass = ANALYZERS.get(engine_name)
    if not AnalyzerClass:
        raise ValueError(f"Unknown sentiment engine: {engine_name}")
    return AnalyzerClass()


# --- Main Lambda Handler (Refactored) ---

def lambda_handler(event, context):
    """
    Receives data, enriches it with sentiment analysis, and stores it.
    """
    print(f"Received event: {event}")
    
    # Get the desired sentiment engine from environment variables
    engine_name = os.environ.get("SENTIMENT_ENGINE", "comprehend")
    analyzer = get_analyzer(engine_name)
    
    try:
        body = json.loads(event.get("body", "{}"))
        posts = body.get("posts", [])
        tenant_id = body.get("tenant_id", "default-tenant")
        topic = body.get("topic", "general")
        
        if not posts:
            return {"statusCode": 400, "body": "No posts found in request body."}
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "Invalid JSON in request body."}

    # 1. Write raw batch to S3 (no changes)
    try:
        now = datetime.utcnow()
        s3_key = f"raw/{now.strftime('%Y/%m/%d')}/{uuid.uuid4()}.json"
        s3.put_object(Bucket=DATA_LAKE_BUCKET, Key=s3_key, Body=json.dumps(body))
        print(f"Successfully wrote raw batch to S3: {s3_key}")
    except Exception as e:
        print(f"Error writing to S3: {e}")
        raise e

    # 2. Enrich and write each post to DynamoDB (UPDATED)
    try:
        with table.batch_writer() as batch:
            for post in posts:
                # *** NEW: Perform sentiment analysis ***
                sentiment_result = analyzer.detect_sentiment(post["text"])
                
                item = {
                    "PK": f"{tenant_id}#{topic}",
                    "SK": f"{post['timestamp']}#{post['id']}",
                    "id": post["id"],
                    "text": post["text"],
                    "author": post["author"],
                    "timestamp": post["timestamp"],
                    "source": post["source"],
                    # *** NEW: Add sentiment data to the item ***
                    "sentiment": sentiment_result.get("Sentiment"),
                    "sentiment_score_positive": str(sentiment_result.get("SentimentScore", {}).get("Positive", 0)),
                    "sentiment_score_negative": str(sentiment_result.get("SentimentScore", {}).get("Negative", 0)),
                    "sentiment_score_neutral": str(sentiment_result.get("SentimentScore", {}).get("Neutral", 0)),
                    "sentiment_score_mixed": str(sentiment_result.get("SentimentScore", {}).get("Mixed", 0)),
                }
                batch.put_item(Item=item)
        print(f"Successfully wrote {len(posts)} enriched items to DynamoDB.")
    except Exception as e:
        print(f"Error writing to DynamoDB: {e}")
        raise e

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Data processed and enriched successfully"})
    }