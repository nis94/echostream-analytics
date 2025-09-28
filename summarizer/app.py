import os
import json
import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timedelta, timezone

# --- Boto3 Clients ---
bedrock_client = boto3.client(service_name="bedrock-runtime") 
ses_client = boto3.client("ses") # <-- NEW SES client
dynamodb = boto3.resource("dynamodb")

# --- Configuration ---
DATA_TABLE_NAME = os.environ.get("DATA_TABLE")
TENANTS_TABLE_NAME = os.environ.get("TENANTS_TABLE")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL") # <-- NEW env var
data_table = dynamodb.Table(DATA_TABLE_NAME)
tenants_table = dynamodb.Table(TENANTS_TABLE_NAME)

# --- Helper Functions (get_active_tenants, get_recent_posts_for_tenant, generate_summary_with_bedrock are unchanged) ---
# ... (paste your existing helper functions here to keep them)

def get_active_tenants():
    print("Fetching active tenants from DynamoDB...")
    response = tenants_table.scan(FilterExpression=boto3.dynamodb.conditions.Attr('is_active').eq(True))
    tenants = response.get('Items', [])
    print(f"Found {len(tenants)} active tenants.")
    return tenants

def get_recent_posts_for_tenant(tenant):
    """Queries the main data table for recent posts for a given tenant."""
    print(f"Fetching recent posts for tenant: {tenant['tenant_id']}")
    all_posts = []
    # Calculate the timestamp for 24 hours ago
    time_24_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    # --- FIX: Iterate through the new 'watchlist' attribute ---
    for item in tenant.get('watchlist', []):
        topic = item.get('topic')
        if not topic:
            continue
            
        pk = f"{tenant['tenant_id']}#{topic}"
        response = data_table.query(
            KeyConditionExpression=Key("PK").eq(pk) & Key("SK").gt(time_24_hours_ago),
            ScanIndexForward=False # Newest first
        )
        all_posts.extend(response.get('Items', []))
    
    print(f"Found {len(all_posts)} posts in the last 24 hours for this tenant.")
    return all_posts

def generate_summary_with_bedrock(posts):
    if not posts:
        return "No recent activity to summarize."
    posts.sort(key=lambda x: x.get('sentiment_score_positive', 0), reverse=True)
    text_to_summarize = "\n".join([p['text'] for p in posts[:20]])
    prompt = f"""\nYou are a social media analyst. Based on the following recent comments, provide a concise, 3-bullet-point summary of the key themes and overall sentiment.
    Focus on the most frequently mentioned topics and the strongest opinions.\n\n<comments>\n{text_to_summarize}\n</comments>\n\nSummary:"""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31", "max_tokens": 512,
        "messages": [{"role": "user", "content": prompt}]
    })
    print("Invoking Bedrock with Claude 3 Sonnet model...")
    response = bedrock_client.invoke_model(body=body, modelId="anthropic.claude-3-sonnet-20240229-v1:0")
    response_body = json.loads(response.get("body").read())
    summary = response_body.get("content", [{}])[0].get("text", "Failed to generate summary.")
    print(f"Received summary from Bedrock: {summary}")
    return summary

def save_summary(tenant_id, summary):
    print(f"Saving summary for tenant: {tenant_id}")
    tenants_table.update_item(
        Key={'tenant_id': tenant_id},
        UpdateExpression="SET latest_summary = :s, summary_updated_at = :t",
        ExpressionAttributeValues={':s': summary, ':t': datetime.now(timezone.utc).isoformat()}
    )
    print("Summary saved successfully.")

# --- NEW HELPER FUNCTION ---
def send_summary_email(tenant, summary):
    """Constructs and sends the summary email digest using SES."""
    recipient = tenant.get('contact_email')
    if not recipient:
        print(f"Tenant {tenant['tenant_id']} has no contact_email. Skipping email.")
        return

    subject = f"Your Daily EchoStream Digest for {tenant.get('tenant_name', '')}"
    body_html = f"""
    <html>
    <head></head>
    <body style="font-family: sans-serif;">
      <h1>🌊 EchoStream Daily Digest</h1>
      <p>Hi {tenant.get('tenant_name', 'there')},</p>
      <p>Here is your AI-generated summary of the latest conversations for your tracked topics:</p>
      <div style="background-color: #f4f5f7; border-left: 4px solid #007bff; padding: 15px; margin: 1em 0;">
        <p style="white-space: pre-wrap;">{summary}</p>
      </div>
      <p>Log in to your dashboard to explore the raw data.</p>
      <p>Thanks,<br/>The EchoStream Analytics Team</p>
    </body>
    </html>
    """
    
    print(f"Sending daily digest to {recipient}...")
    ses_client.send_email(
        Source=SENDER_EMAIL,
        Destination={'ToAddresses': [recipient]},
        Message={'Subject': {'Data': subject}, 'Body': {'Html': {'Data': body_html}}}
    )
    print("Email sent successfully.")

# --- Main Lambda Handler (UPDATED) ---
def lambda_handler(event, context):
    """
    Main function triggered by EventBridge Scheduler.
    """
    print("Starting daily summary and email digest process...")
    active_tenants = get_active_tenants()

    for tenant in active_tenants:
        try:
            posts = get_recent_posts_for_tenant(tenant)
            summary = generate_summary_with_bedrock(posts)
            save_summary(tenant['tenant_id'], summary)
            # --- NEW STEP: Send the email ---
            send_summary_email(tenant, summary)
        except Exception as e:
            print(f"Failed to process tenant {tenant.get('tenant_id')}. Error: {e}")
            continue

    return {
        'statusCode': 200,
        'body': json.dumps(f"Successfully processed {len(active_tenants)} tenants.")
    }