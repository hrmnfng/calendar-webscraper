'''
This client is used to generate iCal events based on a given a set of times and game details.
'''

from ics import Calendar, Event
from datetime import datetime

class iCalClient:
    '''
    This is a class for creating calendar events using iCal

    Attributes:
        name (str): Name of the class-object being created.
        calendar (Obj): Calendar object from iCal library.

    Methods:
        add_event(event_name:str, event_time:dateime, event_location:str): Adds an calendar event to the object.
        genereate_ical_data(): Returns a iCal data string for all added calendar events.
    '''
    
    def __init__(self, name):
        self.name = name
        self.calendar = Calendar()
        print(f"Created calendar object with name '{name}'")

    def add_event(self, event_name:str, event_time:datetime, event_location:str):
        '''
        Generate an event given a round name and event time.

        Args:
            round_name (str): Name of the event to be created.
            event_time (datetime obj): Time of the game
            location (str): Location of game

        Returns:
            Void - adds a calendar event to the object.
        '''

        event = Event()
        event.name = event_name
        event.begin = event_time
        event.location = event_location

        self.calendar.events.add(event)

    def generate_ical_data(self):
        '''
        Generates an iCal data string based on a set of calendar events.

        Args:
            self (obj): Calendar object being passed through containing a set of events.

        Returns:
            iCal data string
        '''
        return str(self.calendar)