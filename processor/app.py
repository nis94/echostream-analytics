import os
import json
import boto3 # Make sure boto3 is imported
import uuid
from datetime import datetime
import base64

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

class NLTKSentimentAnalyzer:
    """Uses a self-hosted NLTK model to detect sentiment."""
    def __init__(self):
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
        import nltk

        # NLTK data needs to be loaded from the Lambda Layer path
        nltk.data.path.append("/opt/python/nltk_data")
        # Initialize the analyzer once per container reuse
        self.analyzer = SentimentIntensityAnalyzer()

    def detect_sentiment(self, text):
        print(f"Running NLTK VADER for text: {text[:100]}...")
        
        # Get scores from VADER
        scores = self.analyzer.polarity_scores(text)
        
        # Determine the overall sentiment based on the compound score
        if scores['compound'] >= 0.05:
            sentiment = 'POSITIVE'
        elif scores['compound'] <= -0.05:
            sentiment = 'NEGATIVE'
        else:
            sentiment = 'NEUTRAL'
            
        # Format the output to match the structure of the Comprehend response
        return {
            "Sentiment": sentiment,
            "SentimentScore": {
                "Positive": scores['pos'],
                "Negative": scores['neg'],
                "Neutral": scores['neu'],
                "Mixed": 0 # VADER doesn't have a mixed score, so we'll default to 0
            }
        }
    
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


# --- Main Lambda Handler (Refactored for Kinesis) ---
def lambda_handler(event, context):
    print(f"Received Kinesis event with {len(event.get('Records', []))} records.")
    
    engine_name = os.environ.get("SENTIMENT_ENGINE", "comprehend")
    analyzer = get_analyzer(engine_name)
    
    posts_to_process = []
    # --- NEW: KINESIS EVENT PARSING LOGIC ---
    for record in event.get('Records', []):
        try:
            # Kinesis data is base64 encoded, so we must decode it
            payload_bytes = base64.b64decode(record['kinesis']['data'])
            post = json.loads(payload_bytes)
            posts_to_process.append(post)
        except Exception as e:
            print(f"Could not decode or parse record. Skipping. Error: {e}")
            continue # Move to the next record

    if not posts_to_process:
        print("No processable posts found in the event. Exiting.")
        return
        
    # For our v2.0 stream, let's use a fixed tenant/topic for now
    tenant_id = "tenant-kinesis-001"
    topic = "live-reddit-stream"

    # --- UPDATED: Write each post to S3 and DynamoDB ---
    try:
        with table.batch_writer() as batch:
            for post in posts_to_process:
                # 1. Write the raw post to S3
                now = datetime.utcnow()
                s3_key = f"raw/{tenant_id}/{topic}/{now.strftime('%Y/%m/%d')}/{post['id']}.json"
                s3.put_object(Bucket=DATA_LAKE_BUCKET, Key=s3_key, Body=json.dumps(post))
                
                # 2. Enrich the post with sentiment
                sentiment_result = analyzer.detect_sentiment(post["text"])
                
                # 3. Prepare and write the enriched item to DynamoDB
                item = {
                    "PK": f"{tenant_id}#{topic}",
                    "SK": f"{post['timestamp']}#{post['id']}",
                    "id": post["id"],
                    "text": post["text"],
                    "author": post["author"],
                    "timestamp": post["timestamp"],
                    "source": post["source"],
                    "sentiment": sentiment_result.get("Sentiment"),
                    "sentiment_score_positive": str(sentiment_result.get("SentimentScore", {}).get("Positive", 0)),
                    "sentiment_score_negative": str(sentiment_result.get("SentimentScore", {}).get("Negative", 0)),
                    "sentiment_score_neutral": str(sentiment_result.get("SentimentScore", {}).get("Neutral", 0)),
                    "sentiment_score_mixed": str(sentiment_result.get("SentimentScore", {}).get("Mixed", 0)),
                }
                batch.put_item(Item=item)

        print(f"Successfully processed and stored {len(posts_to_process)} posts.")
    except Exception as e:
        print(f"Error during S3/DynamoDB processing: {e}")
        raise e

    return {
        "statusCode": 200,
        "body": "Successfully processed records."
    }