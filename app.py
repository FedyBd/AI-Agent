import os
import pickle
import pandas as pd
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import datetime
import google.generativeai as genai
import json
import re
import dateparser  
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Constants from .env
SCOPES = ['https://www.googleapis.com/auth/calendar']
CSV_FILE = os.getenv('CSV_FILE', 'contacts.csv')  # Default to 'contacts.csv' if not set
CREDENTIALS_PATH = os.getenv('CREDENTIALS_PATH', 'credentials.json')
TOKEN_PATH = os.getenv('TOKEN_PATH', '../token.pickle')
API_KEY = os.getenv('GOOGLE_API_KEY')  # API Key from .env

# Step 1: Frame the prompt properly to extract key info
def analyze_prompt(query):
    # Create the request body with the formatted prompt
    prompt =  (
        f"Analyze the following prompt: '{query}'. "
        f"Extract the following information: "
        f"1. The recipient's name. "
        f"2. The date and time of the meeting. "
        f"3. A flag 'task' with value 1 if the task is scheduling a meeting, 0 otherwise. "
        f"Return the result in a JSON format."
    )

    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)

        # Clean the response text using regex
        cleaned_response = re.sub(r"```(?:json)?|```", "", response.text).strip()

        return json.loads(cleaned_response)
    except Exception as e:
        print("Error:", e)
        return None

# Step 2: CSV lookup for email
def get_email(name, csv_file=CSV_FILE):
    data = pd.read_csv(csv_file)
    result = data[data['Name'] == name]
    return result['Email'].iloc[0] if not result.empty else None

def authenticate_google():
    creds = None
    # Path to token.pickle
    token_path = TOKEN_PATH

    # Check if token.pickle exists
    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    # If no (valid) credentials are available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=76, prompt='consent')

        # Save the credentials for the next run
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)

    # Return the Calendar API service object
    return build('calendar', 'v3', credentials=creds)

# Step 4: Schedule Meeting
def schedule_meeting(name, email, start_time_str):
    # Parse the start time from the string using dateparser
    start_time = dateparser.parse(start_time_str)

    if not start_time:
        print(f"Error: Unable to parse the date and time from the string: '{start_time_str}'")
        return

    # Convert parsed datetime to ISO format for Google Calendar
    start_time_iso = start_time.isoformat()

    service = authenticate_google()

    # Define meeting details
    event = {
        'summary': f"Meeting with {name}",
        'start': {'dateTime': start_time_iso, 'timeZone': 'UTC'},
        'end': {'dateTime': (start_time + datetime.timedelta(hours=1)).isoformat(), 'timeZone': 'UTC'},
        'attendees': [{'email': email}],
        'conferenceData': {'createRequest': {'requestId': 'sample123'}}
    }

    event = service.events().insert(
        calendarId='primary',
        body=event,
        conferenceDataVersion=1
    ).execute()

    print(f"Meeting scheduled successfully: {event['htmlLink']}")

# Step 5: Process the Query
def process_query(prompt):
    # Analyze the prompt with Llama 3.1 via Ollama
    task_info = analyze_prompt(prompt)

    if not task_info:
        print("Error: Could not extract task from the prompt.")
        return

    # Check if the task is to schedule a meeting
    if task_info["task"] != 1:
        print("Error: Unsupported task.")
        return

    # Retrieve email from CSV
    email = get_email(task_info["recipient"], CSV_FILE)
    if not email:
        print("Error: Email not found.")
        return

    # Schedule the meeting
    schedule_meeting(task_info["recipient"], email, task_info["date_time"])

def run_app():
    while True:
        # Step 6: Ask the user for a query
        query = input("Please enter your query (or type 'exit' to quit): ")

        # Check if the user wants to exit the app
        if query.lower() == 'exit':
            print("Goodbye!")
            break

        # Process the query
        process_query(query)

        # Ask if the user needs anything else
        continue_response = input("Do you need anything else? (yes/no): ").lower()
        if continue_response != 'yes':
            print("Goodbye!")
            break

# Run the app
run_app()
