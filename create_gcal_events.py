from pprint import pprint
import os
import json

from libs.scraper_client import ScraperClient
from libs.google_cal_client import GoogleCalClient

ATTENDEES = json.loads(os.environ['RECIPIENTS'])
URL = os.environ['SCHEDULE_URL']

def simplify_existing_events(existing_events_list):
    '''
    Args:
        existing_events_list (dict): The existing events list returned by the google_cal_client.list_events() function.

    Returns:
        Dict containining simplified list of start time, url and event id.
    '''
    events_simple = {}

    for event in existing_events_list['items']:
        time = event['start']['dateTime'][:-6]
        url = event['extendedProperties']['private']['schedule']
        events_simple.update({time: {"url":url, "id":event["id"]}})

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

def check_attendees():
    '''
    Args:
        html_content (str): The html content in string format that needs to be parsed.
        type (str): The specific parse method.
        custom_parse (dict): Optional param to speciy custom fields to parse.

    Returns:
        Private method for parsing differnt HTML pages.
    '''
    return "test"


# create the scraper client and scrape
htmlScraper = ScraperClient("Peter Parker", URL)

html_content = htmlScraper.get_html()
game_data = htmlScraper.scrape_events(html_content=html_content, parse_type="ssb")
# pprint(game_data)

# create Google Calendar client
GClient = GoogleCalClient("Cal.Endar", os.environ['GCAL_CLIENT_ID'], os.environ['GCAL_CLIENT_SECRET'], os.environ['GCAL_REFRESH_TOKEN'])

# get list of all events
all_events = GClient.list_events()

if len(all_events['items']) == 0:
    empty = True
else:
    empty = False

    # create a simplified dict of existing events
    events_simple = simplify_existing_events(all_events)

# iterate through the scraped game data
for game in game_data:
    round_name = game["round"]
    tip_off = game["start"].strftime("%Y-%m-%dT%H:%M:%S")
    finish = game["end"].strftime("%Y-%m-%dT%H:%M:%S")     
    venue = game["location"]

    # add all games in events list is empty
    if empty: #TODO probably not super efficient to check this every time - maybe move to the start?
        print(f"\n---\n[{round_name}] is a new event - Creating calendar event:")
        new_event = GClient.create_event(event_name=round_name, start_time=tip_off, end_time=finish, attendees=ATTENDEES, location=venue, private_properties={"schedule":URL})
        print(f'Event [{new_event}] created for [{round_name}]')

    # the events list is not empty, check which are new/updated and add them
    else:
        # OPTION 1: there is a perfect match for this event - skip
        if (tip_off in events_simple) and (events_simple[tip_off]['url'] == URL):
            print(f"\n---\n[{round_name}] already has an existing event - Skipping")

        # OPTION 2: there is a partial match for game date but not time - patch
        elif any(tip_off[:-9] in date for date in events_simple.keys()):

            # get a list of all events that match date only
            matching_dates = [date for date in events_simple if tip_off[:-9] in date]
            same_schedule_found = False

            # loop through events that match date and check associated schedule
            for matched_date in matching_dates:

                # if these events also belong to the same schedule/URL then update the round name & time
                if events_simple[matched_date]['url'] == URL:
                    print(f"\n---\n[{round_name}] has an existing event with a different start time - Updating:")
                    patch_details = generate_patch_details(round_name=round_name, tip_off=tip_off, finish=finish)
                    p_id = events_simple[matched_date]['id']
                    patched_event = GClient.patch_event(event_id=p_id, patched_fields=patch_details)

                    print(f'\tEvent for [{round_name}] patched with updated time [{tip_off}]')
                    same_schedule_found = True
                    break

            # OPTION 3A: otherwise all matches belong to a different schedule - insert
            if not(same_schedule_found):
                print(f"\n---\n[{round_name}] is a new event - Creating calendar event:")
                new_event = GClient.create_event(event_name=round_name, start_time=tip_off, end_time=finish, attendees=ATTENDEES, location=venue, private_properties={"schedule":URL})
                print(f'Event [{new_event}] created for [{round_name}]')
            
        # OPTION 3B: there is no match at all - insert
        else:
            print(f"\n---\n[{round_name}] is a new event - Creating calendar event:")
            new_event = GClient.create_event(event_name=round_name, start_time=tip_off, end_time=finish, attendees=ATTENDEES, location=venue, private_properties={"schedule":URL})
            print(f'Event [{new_event}] created for [{round_name}]')


