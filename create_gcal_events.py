import os
import json
import pandas as pd

from helpers.ascii_strings import IMPORTANT_STUFF_1, IMPORTANT_STUFF_2, IMPORTANT_STUFF_3
from libs.scraper_client import ScraperClient
from libs.google_cal_client import GoogleCalClient

ATTENDEES = json.loads(os.environ['RECIPIENTS'])
URL = os.environ['SCHEDULE_URL']

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


def create_new_event(GClient, round_name, tip_off, finish, attendees, venue, url): #TODO will need to add event colours to this
    '''
    Args:
        GClient (obj): Google Calendar client to execute scripts.
        round_name (str): Used for the event title.
        tip_off (str): Start time of the game.
        finish (str): Finsih time of the game.
        attendees (list): List containing email key-value pairs.
        venue (str): Venue of match.
        url (str): Schedule url.

    Returns:
        Private method for parsing differnt HTML pages.
    '''
    print(f'\n---\n[{round_name}] is a new event - Creating calendar event:')
    new_event = GClient.create_event(event_name=round_name, start_time=tip_off, end_time=finish, attendees=attendees, location=venue, private_properties={'schedule':url})
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


def generate_patch_details(round_name:str, tip_off:str, finish:str):
    '''
    Args:
        round_name (str): The name of the round, updated just in case.
        tip_off (str): The new start time for the event.
        finish (str): The new end time for the event.

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
                        }
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
all_events = GClient.list_events()
existing_schedule_events = get_events_by_schedule(existing_events_list=all_events, schedule_url=URL)

# PART 1: check game exists / time is accurate
print(IMPORTANT_STUFF_1)

# the existing google calendar is empty - add all games
if len(existing_schedule_events) == 0:
    for game in game_data:

        round_name, tip_off, finish, venue = get_game_details(game)
        create_new_event(GClient=GClient, round_name=round_name, tip_off=tip_off, finish=finish, attendees=ATTENDEES, venue=venue, url=URL)

# the existing google calendar is not empty - check which are new/updated and add them
else:
    events_simple = simplify_existing_events(existing_schedule_events)

    for game in game_data: # looping through HTML data, not GCal data
        
        round_name, tip_off, finish, venue = get_game_details(game)

        # OPTION 1: there is a perfect match for this event - skip
        if (tip_off in events_simple) and (events_simple[tip_off]['url'] == URL):
            print(f'\n---\n[{round_name}] already has an existing event - Skipping')

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
                    patch_details = generate_patch_details(round_name=round_name, tip_off=tip_off, finish=finish)
                    p_id = events_simple[matched_date]['id']
                    patched_event = GClient.patch_event(event_id=p_id, patched_fields=patch_details)

                    print(f'\tEvent for [{round_name}] patched with updated time [{tip_off}]')
                    same_schedule_found = True
                    break

            # OPTION 3A: otherwise all matches belong to a different schedule - insert
            if not(same_schedule_found):
                create_new_event(GClient=GClient, round_name=round_name, tip_off=tip_off, finish=finish, attendees=ATTENDEES, venue=venue, url=URL)
            
        # OPTION 3B: there is no match at all - insert
        else:
            create_new_event(GClient=GClient, round_name=round_name, tip_off=tip_off, finish=finish, attendees=ATTENDEES, venue=venue, url=URL)

    # PART 2: check users are correct
    print(IMPORTANT_STUFF_2)

    for event in existing_schedule_events:

        changed = False

        try:  
            my_attendeez = event['attendees']
            df = pd.DataFrame(my_attendeez)
            
            #check if provided emails in env variable (new_attendee) is in existing calendar event
            for new_attendee in ATTENDEES:

                # add this email to list to attendees if missing
                if new_attendee['email'] not in df.values.flatten():
                    my_attendeez.append({'email': new_attendee['email'], 'responseStatus': 'needsAction'})
                    changed = True

            if changed:
                # pull down current event and do a partial update to the attendees section
                my_event = GClient.get_event_details(event['id'])
                my_event['attendees'] = my_attendeez
                
                print(f'\n---\nUpdating attendees for event [{my_event["summary"]}]:')
                updated_event = GClient.update_event(event_id=event['id'], updated_event=my_event)
                print(f'\t{updated_event["updated"]}\n\t{my_attendeez}')
        
        # catches the exception if the event has no attendees and adds all provided emails
        except KeyError:
            print(f'\n---\nUpdating attendees for event [{event["summary"]}]:')

            patched_event = GClient.patch_event(event_id=event['id'], patched_fields={'attendees': my_attendeez})
            print(f'\tAdded the following users:\n\t{my_attendeez}')
            
print(IMPORTANT_STUFF_3)
