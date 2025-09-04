import os
import json
import boto3
import uuid
from datetime import datetime

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

# Get table and bucket names from environment variables
DATA_LAKE_BUCKET = os.environ.get("DATA_LAKE_BUCKET")
DATA_TABLE = os.environ.get("DATA_TABLE")
table = dynamodb.Table(DATA_TABLE)

def lambda_handler(event, context):
    """
    Receives a batch of social media posts from API Gateway,
    writes the raw batch to S3, and writes individual posts to DynamoDB.
    """
    print(f"Received event: {event}")
    
    # The actual body is a JSON string, so we need to parse it.
    try:
        body = json.loads(event.get("body", "{}"))
        posts = body.get("posts", [])
        tenant_id = body.get("tenant_id", "default-tenant")
        topic = body.get("topic", "general")
        
        if not posts:
            return {"statusCode": 400, "body": "No posts found in request body."}
            
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "Invalid JSON in request body."}

    # 1. Write the raw, complete batch to our S3 Data Lake
    try:
        now = datetime.utcnow()
        s3_key = f"raw/{now.strftime('%Y/%m/%d')}/{uuid.uuid4()}.json"
        
        s3.put_object(
            Bucket=DATA_LAKE_BUCKET,
            Key=s3_key,
            Body=json.dumps(body)
        )
        print(f"Successfully wrote raw batch to S3: {s3_key}")
    except Exception as e:
        print(f"Error writing to S3: {e}")
        # Decide if you want to fail the whole batch or just log and continue
        # For now, we will fail
        raise e

    # 2. Write each individual post to our DynamoDB table
    try:
        with table.batch_writer() as batch:
            for post in posts:
                item = {
                    "PK": f"{tenant_id}#{topic}",
                    "SK": f"{post['timestamp']}#{post['id']}",
                    "id": post["id"],
                    "text": post["text"],
                    "author": post["author"],
                    "timestamp": post["timestamp"],
                    "source": post["source"]
                }
                batch.put_item(Item=item)
        print(f"Successfully wrote {len(posts)} items to DynamoDB.")
    except Exception as e:
        print(f"Error writing to DynamoDB: {e}")
        raise e

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Data processed successfully",
            "s3_key": s3_key,
            "dynamodb_items": len(posts)
        })
    }