import os
import json
import boto3
import uuid
from datetime import datetime, timezone

# Boto3 Kinesis client
kinesis_client = boto3.client("kinesis")

# Get the Kinesis stream name from an environment variable
STREAM_NAME = os.environ.get("STREAM_NAME")

def lambda_handler(event, context):
    """
    Generates a batch of mock social media posts and sends them to
    the Kinesis Data Stream.
    """
    texts = [
        "This is a mock post for our Kinesis pipeline.", 
        "I absolutely love this new feature! It's amazing!", 
        "This is the worst user experience I've ever had. It's terrible."
    ]

    records = []
    for text_content in texts:
        now = datetime.now(timezone.utc)
        post = {
            "id": f"post-{uuid.uuid4()}",
            "text": text_content,
            "author": f"mock_user_{uuid.uuid4()}",
            "timestamp": now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            "source": "RedditMock"
        }
        
        # Kinesis requires a list of records, each with 'Data' and a 'PartitionKey'
        record = {
            "Data": json.dumps(post).encode("utf-8"),
            "PartitionKey": str(uuid.uuid4()) # Use a random UUID for even distribution
        }
        records.append(record)

    # The full payload sent to the Processor Lambda will be structured by Kinesis
    # Here we just create the top-level keys that our Processor expects
    payload = {
        "tenant_id": "tenant-789",
        "topic": "kinesis-test",
        "posts": records # Note: This structure will be slightly different after Kinesis processing
    }

    try:
        print(f"Sending {len(records)} records to Kinesis stream: {STREAM_NAME}")
        
        # Use put_records for batching, which is more efficient
        response = kinesis_client.put_records(
            StreamName=STREAM_NAME,
            Records=records
        )
        
        print(f"Kinesis response: {response}")
        
        return {
            "statusCode": 200,
            "body": f"Successfully sent {len(records)} records to Kinesis."
        }
        
    except Exception as e:
        print(f"Error sending data to Kinesis: {e}")
        raise e