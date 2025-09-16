import os
import json
import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timedelta, timezone

# --- Boto3 Clients ---
# Use 'bedrock-runtime' to invoke models
bedrock_client = boto3.client(service_name="bedrock-runtime") 
dynamodb = boto3.resource("dynamodb")

# --- Configuration ---
DATA_TABLE_NAME = os.environ.get("DATA_TABLE")
TENANTS_TABLE_NAME = os.environ.get("TENANTS_TABLE")
data_table = dynamodb.Table(DATA_TABLE_NAME)
tenants_table = dynamodb.Table(TENANTS_TABLE_NAME)

# --- Helper Functions ---

def get_active_tenants():
    """Scans the TenantsTable to find all tenants with is_active = true."""
    print("Fetching active tenants from DynamoDB...")
    response = tenants_table.scan(FilterExpression=Key('is_active').eq(True))
    tenants = response.get('Items', [])
    print(f"Found {len(tenants)} active tenants.")
    return tenants

def get_recent_posts_for_tenant(tenant):
    """Queries the main data table for recent posts for a given tenant."""
    print(f"Fetching recent posts for tenant: {tenant['tenant_id']}")
    all_posts = []
    # Calculate the timestamp for 24 hours ago
    time_24_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    for topic in tenant.get('subreddits', []):
        pk = f"{tenant['tenant_id']}#{topic}"
        response = data_table.query(
            KeyConditionExpression=Key("PK").eq(pk) & Key("SK").gt(time_24_hours_ago),
            ScanIndexForward=False # Newest first
        )
        all_posts.extend(response.get('Items', []))
    
    print(f"Found {len(all_posts)} posts in the last 24 hours for this tenant.")
    return all_posts

def generate_summary_with_bedrock(posts):
    """Uses Bedrock and Claude Sonnet to generate a summary of posts."""
    if not posts:
        return "No recent activity to summarize."

    # Prepare the text from posts for the prompt
    # We'll take the top 20 most impactful posts (simple sort by positive score)
    posts.sort(key=lambda x: x.get('sentiment_score_positive', 0), reverse=True)
    text_to_summarize = "\n".join([p['text'] for p in posts[:20]])

    # This is the prompt that instructs the AI
    prompt = f"""
    You are a social media analyst. Based on the following recent comments, provide a concise, 3-bullet-point summary of the key themes and overall sentiment.
    Focus on the most frequently mentioned topics and the strongest opinions.

    <comments>
    {text_to_summarize}
    </comments>

    Summary:
    """

    # Claude 3 Sonnet Request Body
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        "messages": [{"role": "user", "content": prompt}]
    })

    print("Invoking Bedrock with Claude 3 Sonnet model...")
    response = bedrock_client.invoke_model(
        body=body, 
        modelId="anthropic.claude-3-sonnet-20240229-v1:0"
    )
    
    response_body = json.loads(response.get("body").read())
    summary = response_body.get("content", [{}])[0].get("text", "Failed to generate summary.")
    
    print(f"Received summary from Bedrock: {summary}")
    return summary

def save_summary(tenant_id, summary):
    """Saves the generated summary back to the TenantsTable."""
    print(f"Saving summary for tenant: {tenant_id}")
    tenants_table.update_item(
        Key={'tenant_id': tenant_id},
        UpdateExpression="SET latest_summary = :s, summary_updated_at = :t",
        ExpressionAttributeValues={
            ':s': summary,
            ':t': datetime.now(timezone.utc).isoformat()
        }
    )
    print("Summary saved successfully.")


# --- Main Lambda Handler ---
def lambda_handler(event, context):
    """
    Main function triggered by EventBridge Scheduler.
    """
    print("Starting hourly summary generation process...")
    active_tenants = get_active_tenants()

    for tenant in active_tenants:
        try:
            posts = get_recent_posts_for_tenant(tenant)
            summary = generate_summary_with_bedrock(posts)
            save_summary(tenant['tenant_id'], summary)
        except Exception as e:
            print(f"Failed to process tenant {tenant.get('tenant_id')}. Error: {e}")
            continue # Continue to the next tenant

    return {
        'statusCode': 200,
        'body': json.dumps(f"Successfully processed {len(active_tenants)} tenants.")
    }