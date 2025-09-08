import streamlit as st
import requests
import pandas as pd

# --- Page Configuration ---
st.set_page_config(
    page_title="EchoStream Analytics",
    page_icon="🌊",
    layout="wide"
)

# --- CONFIGURATION ---
# Replace this with your actual API Invoke URL
API_INVOKE_URL = "https://qze6bnym65.execute-api.us-east-1.amazonaws.com" 

# --- UI Elements ---
st.title("🌊 EchoStream Analytics Dashboard")
st.write("A dashboard to display real-time social media sentiment.")

# --- Data Fetching and Display ---
# We'll use a form to get user input and a button to trigger the API call
with st.form(key='query_form'):
    st.subheader("Query Parameters")
    # Input fields for tenant and topic
    tenant_id = st.text_input("Tenant ID", value="tenant-456")
    topic = st.text_input("Topic", value="mock-data")
    
    # Submit button for the form
    submit_button = st.form_submit_button(label='Fetch Data')

if submit_button:
    # Construct the full URL with query parameters
    query_url = f"{API_INVOKE_URL}/query?tenant_id={tenant_id}&topic={topic}"
    
    st.info(f"Fetching data from: {query_url}")

    try:
        # Make the GET request to our API
        response = requests.get(query_url)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        
        data = response.json()
        
        if data:
            st.success(f"Successfully fetched {len(data)} posts.")
            # Convert the list of dictionaries to a Pandas DataFrame for better display
            df = pd.DataFrame(data)
            
            # Display the data in an interactive table
            st.dataframe(df)
        else:
            st.warning("Query returned no results. Check if the tenant and topic exist.")

    except requests.exceptions.RequestException as e:
        st.error(f"An error occurred while fetching data: {e}")