import os, sys, json
import pandas as pd

from helpers.ascii_strings import IMPORTANT_STUFF_1, IMPORTANT_STUFF_2, IMPORTANT_STUFF_3
from libs.scraper_client import ScraperClient
from libs.google_cal_client import GoogleCalClient

#TODO: Make these read the YAML file instead
CALENDAR_NAME = os.environ['CALENDAR_NAME'] 
URL = os.environ['SCHEDULE_URL']
EVENT_COLOR_ID = os.environ['EVENT_COLOR_ID'] 
# ATTENDEES = json.loads(os.environ['RECIPIENTS'])


def get_game_details(game):
    round_name = game['round']
    tip_off = game['start'].strftime('%Y-%m-%dT%H:%M:%S')
    finish = game['end'].strftime('%Y-%m-%dT%H:%M:%S')     
    venue = game['location']

    return round_name, tip_off, finish, venue


def get_events_by_schedule(existing_events_list, schedule_url):
    '''
    Args:
        existing_events_list (obj): The full events list returned by the GoogleCalClient.list_events() function.
        schedule_url (str): The schedule URL to match against the extended, private property

    Returns:
        List containing existing events that match the provided schedule url.
    '''
    relevant_events = []

    for event in existing_events_list['items']:
        if event['extendedProperties']['private']['schedule'] == schedule_url:
            relevant_events.append(event)

    return relevant_events


def create_new_event(GClient, calendar_id:str, round_name:str, tip_off:str, finish:str, venue, url:str, color_id:str):
    '''
    Args:
        GClient (obj): Google Calendar client to execute scripts.
        round_name (str): Used for the event title.
        tip_off (str): Start time of the game.
        finish (str): Finsih time of the game.
        venue (str): Venue of match.
        url (str): Schedule url.
        color_id (str): ID for the color of the event.

    Returns:
        Private method for parsing differnt HTML pages.
    '''
    print(f'\n---\n[{round_name}] is a new event - Creating calendar event:')
    new_event = GClient.create_event(calendar_id=calendar_id,event_name=round_name, start_time=tip_off, end_time=finish, location=venue, private_properties={'schedule':url}, color_id=color_id)
    print(f'Event [{new_event}] created for [{round_name}]')


def simplify_existing_events(existing_events_list):
    '''
    Args:
        existing_events_list (dict): The value of ['items'] in the events list returned by the GoogleCalClient.list_events() function.

    Returns:
        Dict containining simplified list of start time, url and event id.
    '''
    events_simple = {}

    for event in existing_events_list:
        time = event['start']['dateTime'][:-6]
        url = event['extendedProperties']['private']['schedule']
        events_simple.update({time: {'url':url, 'id':event['id']}})

    return events_simple


def generate_patch_details(round_name:str, tip_off:str, finish:str, color_id:str):
    '''
    Args:
        round_name (str): The name of the round, updated just in case.
        tip_off (str): The new start time for the event.
        finish (str): The new end time for the event.
        color_id (str): The color for the event

    Returns:
        Dict containing the patch details.
    '''
    patch_details = {
                        'summary': round_name,
                        'start': {
                            'dateTime': tip_off,
                        },
                        'end': {
                            'dateTime': finish, 
                        },
                        'colorId':color_id
                    }
     
    return patch_details


'''
Executes from here onwards
'''
# create the scraper client and scrape
htmlScraper = ScraperClient('Peter Parker', URL)
html_content = htmlScraper.get_html()
game_data = htmlScraper.scrape_events(html_content=html_content, parse_type='ssb')

# create Google Calendar client and get calendar events
GClient = GoogleCalClient('Cal.Endar', os.environ['GCAL_CLIENT_ID'], os.environ['GCAL_CLIENT_SECRET'], os.environ['GCAL_REFRESH_TOKEN'])

# PART 1: check if calendar exists, otherwise create one
print(IMPORTANT_STUFF_1)

calendar_id = ''
calendar_exists = False
calendar_list = GClient.get_calendar_list()

# try to use an existing calendar
for calendar in calendar_list['items']:
    if calendar['summary'] == CALENDAR_NAME:
        calendar_id = calendar['id']
        print(f'\nCalendar [{CALENDAR_NAME}] already exists with id [{calendar_id}]')
        calendar_exists = True
        break

# create a new calendar if one does not already exist
if not calendar_exists:
    descr = f'This calendar has been extracted from "{URL}"'
    print(f'\nCalendar [{CALENDAR_NAME}] does not yet exist - Creating:')
    calendar_id = GClient.insert_calendar(calendar_name=CALENDAR_NAME, description=descr)
    print(f' -> Calendar [{CALENDAR_NAME}] created with id [{calendar_id}]')

if calendar_id == '': sys.exit(f'No Calendar Id has been set: [{calendar_id}]')

# PART 2: check game exists / time is accurate
print(IMPORTANT_STUFF_2)

#TODO: Analysis required to determine if there should be rework to not check schedule URL when matching events
all_events = GClient.list_events(calendar_id=calendar_id) 
existing_schedule_events = get_events_by_schedule(existing_events_list=all_events, schedule_url=URL)

# the existing google calendar is empty - add all games
if len(existing_schedule_events) == 0:
    
    for game in game_data:
        round_name, tip_off, finish, venue = get_game_details(game)
        create_new_event(GClient=GClient, calendar_id=calendar_id, round_name=round_name, tip_off=tip_off, finish=finish, venue=venue, url=URL, color_id=EVENT_COLOR_ID)

# the existing google calendar is not empty - check which are new/updated and add them
else:
    events_simple = simplify_existing_events(existing_schedule_events)

    for game in game_data: # looping through HTML data, not GCal data
        
        round_name, tip_off, finish, venue = get_game_details(game)

        # OPTION 1: there is a perfect match for this event - Update other name/color if necessary
        if (tip_off in events_simple) and (events_simple[tip_off]['url'] == URL):
            print(f'\n---\n[{round_name}] already has an existing event - Checking name/color')

            # update name and color if necessary
            event_details = GClient.get_event_details(calendar_id=calendar_id, event_id=events_simple[tip_off]['id'])
            if (event_details['colorId'] != EVENT_COLOR_ID) or (event_details['summary'] != round_name):
                mini_patch = GClient.patch_event(calendar_id=calendar_id, event_id=events_simple[tip_off]['id'], patched_fields={'summary': round_name, 'colorId': EVENT_COLOR_ID})
                print(f'\tPatched the name/color for event for [{round_name}]')

        # OPTION 2: there is a partial match for game date but not time - patch
        elif any(tip_off[:-9] in date for date in events_simple.keys()):

            # get a list of all events that match date only
            matching_dates = [date for date in events_simple if tip_off[:-9] in date]
            same_schedule_found = False

            # loop through events that match date and check associated schedule
            for matched_date in matching_dates:

                # if these events also belong to the same schedule/URL then update the round name & time
                if events_simple[matched_date]['url'] == URL:
                    print(f'\n---\n[{round_name}] has an existing event with a different start time - Updating:')
                    patch_details = generate_patch_details(round_name=round_name, tip_off=tip_off, finish=finish, color_id=EVENT_COLOR_ID)
                    p_id = events_simple[matched_date]['id']
                    patched_event = GClient.patch_event(calendar_id=calendar_id, event_id=p_id, patched_fields=patch_details)

                    print(f'\tEvent for [{round_name}] patched with updated time [{tip_off}]')
                    same_schedule_found = True
                    break

            # OPTION 3A: otherwise all matches belong to a different schedule - insert
            if not(same_schedule_found):
                create_new_event(GClient=GClient, calendar_id=calendar_id, round_name=round_name, tip_off=tip_off, finish=finish, venue=venue, url=URL, color_id=EVENT_COLOR_ID)
            
        # OPTION 3B: there is no match at all - insert
        else:
            create_new_event(GClient=GClient, calendar_id=calendar_id, round_name=round_name, tip_off=tip_off, finish=finish, venue=venue, url=URL, color_id=EVENT_COLOR_ID)

print(IMPORTANT_STUFF_3)

    # TODO: Remove this
    # # PART 3: check users are correct

    # for event in existing_schedule_events:

    #     changed = False

    #     try:  
    #         my_attendeez = event['attendees']
    #         df = pd.DataFrame(my_attendeez)
            
    #         #check if provided emails in env variable (new_attendee) is in existing calendar event
    #         for new_attendee in ATTENDEES:

    #             # add this email to list to attendees if missing
    #             if new_attendee['email'] not in df.values.flatten():
    #                 my_attendeez.append({'email': new_attendee['email'], 'responseStatus': 'needsAction'})
    #                 changed = True

    #         if changed:
    #             # pull down current event and do a partial update to the attendees section
    #             my_event = GClient.get_event_details(event['id'])
    #             my_event['attendees'] = my_attendeez
                
    #             print(f'\n---\nUpdating attendees for event [{my_event["summary"]}]:')
    #             updated_event = GClient.update_event(event_id=event['id'], updated_event=my_event)
    #             print(f'\t{updated_event["updated"]}\n\t{my_attendeez}')
        
    #     # catches the exception if the event has no attendees and adds all provided emails
    #     except KeyError:
    #         print(f'\n---\nUpdating attendees for event [{event["summary"]}]:')

    #         patched_event = GClient.patch_event(event_id=event['id'], patched_fields={'attendees': my_attendeez})
    #         print(f'\tAdded the following users:\n\t{my_attendeez}')