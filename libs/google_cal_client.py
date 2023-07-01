from googleapiclient.discovery import build
from google.oauth2 import service_account

# Load the credentials from the JSON file
credentials = service_account.Credentials.from_service_account_file('path/to/credentials.json')

# Create a service object for interacting with the Google Calendar API
service = build('calendar', 'v3', credentials=credentials)

# Create a new event
event = {
    'summary': 'My Event',
    'start': {
        'dateTime': '2023-06-30T10:00:00',
        'timeZone': 'Your_Time_Zone',
    },
    'end': {
        'dateTime': '2023-06-30T12:00:00',
        'timeZone': 'Your_Time_Zone',
    },
}

# Insert the event into the calendar
calendar_id = 'primary'  # Use 'primary' for the primary calendar
event = service.events().insert(calendarId=calendar_id, body=event).execute()

# Print the event ID
print('Event created: {}'.format(event.get('id')))