import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/calendar']

class GoogleCalClient:
    '''
    This is a class for creating calendar events using Google Calendar APIs
    It connects to external Gmail account and uses OAuth2.0 for authorisation

    Attributes:
        name (str): Name of the class-object being created.
        gcal_client_id (str): OS env variable passed it for authentication.
        gcal_client_secret (str): OS env variable passed it for authentication.
        gcal_refresh_token (str): OS env variable passed it for authentication.

    Methods:
        create_event(event_name:str, start_time:str, end_time:str, attendees:list, location:str, private_properties:dict, calendar_id:str, visible_attendees:bool, time_zone:str): Creates an Google Calendar event.
        patch_event(event_id:str, updated_fields:dict, calendar_id:str): Updates specified fields in a Google Calendar event.
        list_events(calendar_id:str): Retrives a list of all events in a Google Calendar.
        get_event_details(event_id:str, calendar_id:str): Retrives details for a specified Google Calendar event.
    '''

    def __init__(self, name, gcal_client_id, gcal_client_secret, gcal_refresh_token):
        self.name = name
        self.creds = None

        # Authorise using provided OAuth2.0 credentials
        self.creds = Credentials.from_authorized_user_info(
            {
                'client_id': gcal_client_id,
                'client_secret': gcal_client_secret,
                'refresh_token': gcal_refresh_token
            },
            scopes=SCOPES
        )

        # If credentials missing or invalid, refresh access
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES) #TODO This doesn't make sense in a GitHub actions world as the credentials.json file should never be available
                self.creds = flow.run_local_server(port=0)
            
            # Save the credentials as env variables for the next run
            os.environ['GCAL_CLIENT_ID'] = self.creds.client_id
            os.environ['GCAL_CLIENT_SECRET'] = self.creds.client_secret
            os.environ['GCAL_REFRESH_TOKEN'] = self.creds.refresh_token


        self.service = build('calendar', 'v3', credentials=self.creds)

        print(f"Created GCal client object with name '{name}'")

        # creds = Credentials.from_authorized_user_info(
        #     {
        #         'client_id': os.environ['GCAL_CLIENT_ID'],
        #         'client_secret': os.environ['GCAL_CLIENT_SECRET'],
        #         'refresh_token': os.environ['GCAL_REFRESH_TOKEN']
        #     },
        #     scopes=SCOPES
        # )

    def create_event(self, event_name:str, start_time:str, end_time:str, attendees:list, location:str, private_properties:dict,
                     calendar_id:str='primary', visible_attendees:bool=False, time_zone:str='Australia/Sydney', color_id:int=1):
        '''
        Creates an Google Calendar event.

        Args:
            event_name (str): Name of the event to be created.
            start_time (str): Start time for the event in "%Y-%m-%dT%H:%M:%S" format  e.g. "2023-07-02T10:00:00".
            end_time (str): End time for the event in the above in "%Y-%m-%dT%H:%M:%S" format  e.g. "2023-07-02T10:30:00".
            attendees (list): List of attendees in nested dict format e.g. [{'email': 'person1@gmail.com'}, {'email': 'person2@gmail.com'}].
            location (str): Location of event.
            private_properties (dict): Dict of Key-value pairs for additional tagging.
            calendar_id (str): Calendar to add the event to - default is "primary".
            visibile_attendees (bool): Whether or not attendees are able to see other attendees in the event - default is False
            time_zone (str): Time zone for start and end times - default is "Australia/Sydney"
            color_id (int): Select a color for the created event using predefined options - default is 1, see colors.json for options

        Returns:
            Event ID for the created event.
        '''

        # Create a new event
        new_event = {
            'summary': event_name,
            'start': {
                'dateTime': start_time, # e.g. '2023-07-02T10:00:00'
                'timeZone': time_zone,
            },
            'end': {
                'dateTime': end_time, # e.g. '2023-07-02T10:30:00'
                'timeZone': time_zone,
            },
            'attendees':attendees, # e.g. [{'email': 'person1@gmail.com'}, {'email': 'person2@gmail.com'}]
            'location':location,
            'extendedProperties': {
                "private": private_properties
            },
            'guestsCanSeeOtherGuests': visible_attendees,
            'colorId':color_id # see colors.json for options
        }
        
        # Insert the event into the calendar
        response = self.service.events().insert(calendarId=calendar_id, body=new_event).execute()

        return response.get('id')
    
    def patch_event(self, event_id:str, updated_fields:dict, calendar_id:str='primary'):
        '''
        Updates specified fields in a Google Calendar event.

        Args:
            event_id (str): ID of the event to be updated.
            updated_fields (dict): Fields of the event to be updated.
            calendar_id (str): Calendar of the event being patched - default is "primary".

        Returns:
            Event ID for the updated event.
        '''

        # Fields to be updated
        patch_event = updated_fields
    
        '''
        e.g.
            {
                'summary': 'My Event (Updated)',
                'attendees': [
                    {'email': 'cal.endar.hlpr@gmail.com'},
                    {'email': 'hermes.fng@gmail.com'}
                ]
            }
        '''

        # Update the event in calendar
        repsonse = self.service.events().patch(calendarId=calendar_id, eventId = event_id, body=patch_event).execute()

        return repsonse.get('id')


    def list_events(self, calendar_id:str='primary'):
        '''
        Retrives a list of all events in a Google Calendar.

        Args:.
            calendar_id (str): Calendar to retrieve events list from - default is "primary".

        Returns:
            List of events in given calendar.
        '''

        events_list = self.service.events().list(calendarId=calendar_id).execute()

        return events_list
    

    def get_event_details(self, event_id:str, calendar_id:str='primary'):
        '''
        Retrives details for a specified Google Calendar event.

        Args:
            event_id (str): ID of the event to retrieve details for.
            calendar_id (str): Calendar to retrieve event from - default is "primary".

        Returns:
            Dict containing event details.
        '''

        event_details = self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        return event_details
