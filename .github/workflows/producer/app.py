import os
import json
import uuid
import urllib3
from datetime import datetime, timezone

http = urllib3.PoolManager()

# Get the API endpoint URL from an environment variable
API_ENDPOINT_URL = os.environ.get("API_ENDPOINT_URL")

def lambda_handler(event, context):
    """
    Generates a batch of mock social media posts and sends them to
    the EchoStream Analytics API Gateway endpoint.
    """
    posts = []
    for i in range(3): # Generate 3 mock posts
        now = datetime.now(timezone.utc)
        timestamp = now.strftime('%Y-%m-%dT%H:%M:%SZ')
        post_id = str(uuid.uuid4())
        
        post = {
            "id": f"post-{post_id}",
            "text": f"This is a mock post number {i+1} with a unique ID.",
            "author": f"mock_user_{i+1}",
            "timestamp": timestamp,
            "source": "Mock"
        }
        posts.append(post)

    # This is the payload our ProcessorLambda expects
    payload = {
        "tenant_id": "tenant-456",
        "topic": "mock-data",
        "posts": posts
    }
    
    encoded_payload = json.dumps(payload).encode("utf-8")
    
    headers = {
        "Content-Type": "application/json"
    }

    try:
        print(f"Sending payload to {API_ENDPOINT_URL}")
        resp = http.request(
            "POST",
            API_ENDPOINT_URL,
            body=encoded_payload,
            headers=headers
        )
        
        print(f"Response status: {resp.status}")
        print(f"Response data: {resp.data.decode('utf-8')}")
        
        if resp.status != 200:
            raise Exception("Failed to send data to API")

        return {
            "statusCode": 200,
            "body": "Successfully sent mock data batch."
        }
        
    except Exception as e:
        print(f"Error sending data: {e}")
        raise e