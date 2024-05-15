import os, sys, yaml
import pandas as pd
import logging

from helpers.ascii_strings import IMPORTANT_STUFF_1, IMPORTANT_STUFF_2, IMPORTANT_STUFF_3
from libs.scraper_client import ScraperClient
from libs.google_cal_client import GoogleCalClient


def get_game_details(game):
    '''
    Args:
        game (dict): The game details extracted from the HTML page in dict format.

    Returns:
        Strings containing round name, tip off time, finish time and venue for the provided game.
    '''
    round_name = game['round']
    tip_off = game['start'].strftime('%Y-%m-%dT%H:%M:%S')
    finish = game['end'].strftime('%Y-%m-%dT%H:%M:%S')     
    venue = game['location']
    details_url = game['details_url']

    return round_name, tip_off, finish, venue, details_url


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


def create_new_event(GClient, calendar_id:str, round_name:str, tip_off:str, finish:str, venue, url:str, color_id:str, description:str=""):
    '''
    Args:
        GClient (obj): Google Calendar client to execute scripts.
        round_name (str): Used for the event title.
        tip_off (str): Start time of the game.
        finish (str): Finish time of the game.
        venue (str): Venue of match.
        url (str): Schedule url.
        color_id (str): ID for the color of the event.
        description (str): Description for the event - links to the score for the game.

    Returns:
        Private method for parsing differnt HTML pages.
    '''
    print(f'[{round_name}] is a new event - Creating calendar event:')
    new_event = GClient.create_event(calendar_id=calendar_id,event_name=round_name, start_time=tip_off, end_time=finish, location=venue, private_properties={'schedule':url}, color_id=color_id, description=description)
    print(f'\tEvent [{new_event}] created for [{round_name}]')


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


def generate_patch_details(round_name:str, tip_off:str, finish:str, color_id:str, description:str=""):
    '''
    Args:
        round_name (str): The name of the round, updated just in case.
        tip_off (str): The new start time for the event.
        finish (str): The new end time for the event.
        color_id (str): The color for the event.
        description (str): A description for the event.

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
                        'colorId': color_id
                    }
    
    if description != "" :
        patch_details.update({'description': description})
     
    return patch_details


def main_update_calenders(input_calendar_name:str, input_url:str, input_event_color_id:str):
    # scrape events
    html_content = htmlScraper.get_html(input_url)
    game_data = htmlScraper.scrape_events(html_content=html_content, parse_type='ssb')

    # PART 1: check if calendar exists, otherwise create one
    print(IMPORTANT_STUFF_1)

    calendar_id = ''
    calendar_exists = False
    calendar_list = GClient.get_calendar_list()

    # try to use an existing calendar
    for calendar in calendar_list['items']:
        if calendar['summary'] == input_calendar_name:
            calendar_id = calendar['id']
            print(f'Calendar [{input_calendar_name}] already exists with id [{calendar_id}]')
            calendar_exists = True
            break

    # create a new calendar if one does not already exist
    if not calendar_exists:
        descr = f'This calendar has been extracted from "{input_url}"'
        print(f'Calendar [{input_calendar_name}] does not yet exist - Creating:')
        calendar_id = GClient.insert_calendar(calendar_name=input_calendar_name, description=descr)
        print(f' -> Calendar [{input_calendar_name}] created with id [{calendar_id}]')

    # PART 2: check game exists / time is accurate
    print(IMPORTANT_STUFF_2)

    #TODO: Analysis required to determine if there should be rework to not check schedule URL when matching events
    all_events = GClient.list_events(calendar_id=calendar_id) 
    existing_schedule_events = get_events_by_schedule(existing_events_list=all_events, schedule_url=input_url)

    # the existing google calendar is empty - add all games
    if len(existing_schedule_events) == 0:
        
        for game in game_data:
            round_name, tip_off, finish, venue, details_url = get_game_details(game)
            create_new_event(GClient=GClient, calendar_id=calendar_id, round_name=round_name, tip_off=tip_off, finish=finish, venue=venue, url=input_url, color_id=input_event_color_id)

    # the existing google calendar is not empty - check which are new/updated and add them
    else:
        events_simple = simplify_existing_events(existing_schedule_events)

        for game in game_data: # looping through HTML data, not GCal data
            
            round_name, tip_off, finish, venue, details_url = get_game_details(game)

            # OPTION 1: there is a perfect match for this event - Update other name/color if necessary
            if (tip_off in events_simple) and (events_simple[tip_off]['url'] == input_url):
                print(f'[{round_name}] already has an existing event - Checking details...')

                # update name, color or description if necessary
                # TODO: There's definitely a nicer way to do this
                event_details = GClient.get_event_details(calendar_id=calendar_id, event_id=events_simple[tip_off]['id'])
                
                if event_details['summary'] != round_name:
                    name_patch = GClient.patch_event(calendar_id=calendar_id, event_id=events_simple[tip_off]['id'], patched_fields={'summary': round_name})
                    print(f'\tPatched the name for event for [{round_name}] - id [{name_patch}]')

                if event_details['colorId'] != str(input_event_color_id):
                    color_patch = GClient.patch_event(calendar_id=calendar_id, event_id=events_simple[tip_off]['id'], patched_fields={'colorId': input_event_color_id})
                    print(f'\tPatched the color for event for [{round_name}] - id [{color_patch}]')

                try:
                    if event_details['description'] != details_url:
                        descr_patch = GClient.patch_event(calendar_id=calendar_id, event_id=events_simple[tip_off]['id'], patched_fields={'description': details_url})
                        print(f'\tPatched the description for event for [{round_name}] - id [{descr_patch}]')
                except Exception as e:
                    if e.args[0] == "description":
                        print("\tNo description found - attempting a patch...")
                        descr_patch = GClient.patch_event(calendar_id=calendar_id, event_id=events_simple[tip_off]['id'], patched_fields={'description': details_url})
                        print(f'\tPatched the description for event for [{round_name}] - id [{descr_patch}]')

                if event_details['location'] != venue:
                    loc_patch = GClient.patch_event(calendar_id=calendar_id, event_id=events_simple[tip_off]['id'], patched_fields={'location': venue})
                    print(f'\tPatched the location for event for [{round_name}] - id [{loc_patch}]')

            # OPTION 2: there is a partial match for game date but not time - patch
            elif any(tip_off[:-9] in date for date in events_simple.keys()):

                # get a list of all events that match date only
                matching_dates = [date for date in events_simple if tip_off[:-9] in date]
                same_schedule_found = False

                # loop through events that match date and check associated schedule
                for matched_date in matching_dates:

                    # if these events also belong to the same schedule/URL then update the round name & time
                    if events_simple[matched_date]['url'] == input_url:
                        print(f'[{round_name}] has an existing event with a different start time - Updating:')
                        patch_details = generate_patch_details(round_name=round_name, tip_off=tip_off, finish=finish, color_id=input_event_color_id, description=details_url)
                        p_id = events_simple[matched_date]['id']
                        patched_event = GClient.patch_event(calendar_id=calendar_id, event_id=p_id, patched_fields=patch_details)

                        print(f'\tEvent for [{round_name}] patched with updated time [{tip_off}] - id [{patched_event}]')
                        same_schedule_found = True
                        break

                # OPTION 3A: otherwise all matches belong to a different schedule - insert
                if not(same_schedule_found):
                    create_new_event(GClient=GClient, calendar_id=calendar_id, round_name=round_name, tip_off=tip_off, finish=finish, venue=venue, url=input_url, color_id=input_event_color_id, description=details_url)
                
            # OPTION 3B: there is no match at all - insert
            else:
                create_new_event(GClient=GClient, calendar_id=calendar_id, round_name=round_name, tip_off=tip_off, finish=finish, venue=venue, url=input_url, color_id=input_event_color_id, description=details_url)

    print('\n# Finished reading file')

'''
Executes from here onwards
'''
logger = logging.getLogger(__name__) # TODO: should actually used this :)

# create Scraper and Google Calender Clients
htmlScraper = ScraperClient('Peter Parker')
GClient = GoogleCalClient('Cal.Endar', os.environ['GCAL_CLIENT_ID'], os.environ['GCAL_CLIENT_SECRET'], os.environ['GCAL_REFRESH_TOKEN'])
config_dir = './calendar-configs'

# read and iterate through config files
try:
    if len(os.listdir(config_dir)) == 0:
        sys.exit('Please provide at least one config file in the "calendar-configs" folder')
    else:    
        for filename in os.listdir(config_dir):
            if filename.startswith('config-') and filename.endswith('.yaml'):
                file_path = os.path.join(config_dir, filename)
                
                # Read the YAML file
                with open(file_path, 'r') as file:
                    config_data = yaml.safe_load(file)
                    print(f'\n*************************************************\n# Loaded [{file_path}] #')
                    try: # TODO: you also can't put the whole main function in a try catch block?????
                        main_update_calenders(input_calendar_name=config_data['name'], input_url=config_data['url'], input_event_color_id=config_data['color_id'])
                    except Exception as e:
                        print(f'Something went wrong reading while attempting to read this file:\n{e}')
                        
except FileNotFoundError as e:
    sys.exit('Please ensure that the "calendar-configs" folder has been created and populated in the root directory')

print(IMPORTANT_STUFF_3)