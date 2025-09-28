import os
import json
import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# --- Boto3 Clients ---
ses_client = boto3.client("ses")
dynamodb = boto3.resource("dynamodb")

# --- Configuration ---
DATA_TABLE_NAME = os.environ.get("DATA_TABLE")
TENANTS_TABLE_NAME = os.environ.get("TENANTS_TABLE")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL") # The 'From' address we verified
data_table = dynamodb.Table(DATA_TABLE_NAME)
tenants_table = dynamodb.Table(TENANTS_TABLE_NAME)

# --- Helper to convert DynamoDB's Decimal to float ---
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# --- Helper Functions ---

def get_active_tenants():
    """Scans the TenantsTable to find all tenants with is_active = true."""
    print("Fetching active tenants from DynamoDB...")
    response = tenants_table.scan(FilterExpression=Key('is_active').eq(True))
    tenants = response.get('Items', [])
    print(f"Found {len(tenants)} active tenants.")
    return tenants

def get_average_sentiment(tenant_id, topic, start_time, end_time):
    """
    Queries for posts in a time window and calculates the average net sentiment.
    Net sentiment = (Positive Score - Negative Score)
    """
    pk = f"{tenant_id}#{topic}"
    print(f"Querying for PK: {pk} between {start_time} and {end_time}")
    
    response = data_table.query(
        KeyConditionExpression=Key("PK").eq(pk) & Key("SK").between(start_time, end_time)
    )
    items = response.get("Items", [])
    
    if not items:
        return None # Return None if no posts are found in the window

    total_net_score = 0
    for item in items:
        # DynamoDB numbers can come back as Decimal, so we convert to float
        positive = float(item.get('sentiment_score_positive', 0))
        negative = float(item.get('sentiment_score_negative', 0))
        total_net_score += (positive - negative)
        
    average_score = total_net_score / len(items)
    print(f"Found {len(items)} posts. Average net sentiment: {average_score:.4f}")
    return average_score

def send_alert_email(tenant, topic, old_score, new_score):
    """Constructs and sends an email alert using SES."""
    recipient_email = SENDER_EMAIL # In a real app, this would be tenant['contact_email']
    
    subject = f"🚨 Sentiment Spike Alert for '{topic}'"
    body_html = f"""
    <html>
    <head></head>
    <body>
      <h1>Sentiment Spike Alert</h1>
      <p>Hi {tenant.get('tenant_name', tenant['tenant_id'])},</p>
      <p>Our system has detected a significant negative shift in sentiment for the topic: <b>{topic}</b>.</p>
      <ul>
        <li>Previous 12-hour sentiment score: <b>{old_score:.2f}</b></li>
        <li>Current 12-hour sentiment score: <b style="color:red;">{new_score:.2f}</b></li>
      </ul>
      <p>We recommend you review the latest comments on this topic in your dashboard.</p>
      <p>Thanks,</p>
      <p>The EchoStream Analytics Team</p>
    </body>
    </html>
    """
    
    print(f"Sending alert email to {recipient_email} for topic '{topic}'")
    ses_client.send_email(
        Source=SENDER_EMAIL,
        Destination={'ToAddresses': [recipient_email]},
        Message={
            'Subject': {'Data': subject},
            'Body': {'Html': {'Data': body_html}}
        }
    )

# --- Main Lambda Handler ---
def lambda_handler(event, context):
    """
    Main function triggered by EventBridge Scheduler.
    """
    print("Starting sentiment spike detection process...")
    active_tenants = get_active_tenants()

    # Define our two time windows for comparison
    now = datetime.now(timezone.utc)
    current_window_start = (now - timedelta(hours=12)).isoformat()
    previous_window_start = (now - timedelta(hours=24)).isoformat()

    for tenant in active_tenants:
        # --- FIX: Iterate through the new 'watchlist' attribute ---
        for item in tenant.get('watchlist', []):
            topic = item.get('topic')
            if not topic:
                continue

            try:
                # Get sentiment for the current and previous periods
                new_score = get_average_sentiment(tenant['tenant_id'], topic, current_window_start, now.isoformat())
                old_score = get_average_sentiment(tenant['tenant_id'], topic, previous_window_start, current_window_start)

                if new_score is not None and old_score is not None:
                    # TRIGGER LOGIC: Alert if sentiment is now negative AND has dropped by more than 0.3 points
                    is_now_negative = new_score < -0.1
                    is_significant_drop = new_score < (old_score - 0.3)
                    
                    if is_now_negative and is_significant_drop:
                        send_alert_email(tenant, topic, old_score, new_score)
                else:
                    print(f"Not enough data to compare for topic '{topic}'. Skipping.")

            except Exception as e:
                print(f"Failed to process tenant {tenant.get('tenant_id')} topic '{topic}'. Error: {e}")
                continue

    return {
        'statusCode': 200,
        'body': json.dumps(f"Successfully processed {len(active_tenants)} tenants for alerts.")
    }