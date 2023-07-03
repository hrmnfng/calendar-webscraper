from pprint import pprint
import os
import json

from libs.scraper_client import ScraperClient
from libs.google_cal_client import GoogleCalClient

ATTENDEES = json.loads(os.environ['RECIPIENTS'])
URL = os.environ['SCHEDULE_URL']

# create the scraper client and scrape
dummyScraper = ScraperClient("HTML Scraper", URL)

html_content = dummyScraper.get_html()
game_data = dummyScraper.scrape_events(html_content=html_content, parse_type="ssb")
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
    events_simple = {}
    for event in all_events['items']:
        time = event['start']['dateTime'][:-6]
        url = event['extendedProperties']['private']['schedule']
        events_simple.update({time:url})

# iterate through the scraped game data
for game in game_data:
    round_name = game["round"]
    tip_off = game["start"].strftime("%Y-%m-%dT%H:%M:%S")
    finish = game["end"].strftime("%Y-%m-%dT%H:%M:%S")     
    venue = game["location"]

    # add all games in events list is empty
    if empty:
        print(f"\n---\n[{round_name}] is a new event - Creating calendar event:")
        new_event = GClient.create_event(event_name=round_name, start_time=tip_off, end_time=finish, attendees=ATTENDEES, location=venue, private_properties={"schedule":URL})
        print(f'Event [{new_event}] created for [{round_name}]')

    # the events list is not empty, check which are new/updated and add them
    else:
        # there is a perfect match for this event - skip
        if (tip_off in events_simple) and (events_simple[tip_off] == URL):
            print(f"\n---\n[{round_name}] already has an existing event - Skipping")

        # there is a partial match for game date but not time - patch
        elif any(tip_off[:-9] in date for date in events_simple.keys()):

            # get a list of all events that match date only
            matching_dates = [date for date in events_simple if tip_off[:-9] in date]
            same_schedule_found = False

            for matched_date in matching_dates:

                # if these events also belong to the same schedule/URL then update the time
                if events_simple[matched_date] == URL:
                    print(f"\n---\n[{round_name}] has an existing event with a different start time - Updating:")
                    print("\t\t TO BE DONE HEHE \t\t") #TODO Add Patching
                    same_schedule_found = True
                    break

            # otherwise all matches belong to a different schedule - insert
            if not(same_schedule_found):
                print(f"\n---\n[{round_name}] is a new event - Creating calendar event:")
                new_event = GClient.create_event(event_name=round_name, start_time=tip_off, end_time=finish, attendees=ATTENDEES, location=venue, private_properties={"schedule":URL})
                print(f'Event [{new_event}] created for [{round_name}]')
            
        # there is no match at all - insert
        else:
            print(f"\n---\n[{round_name}] is a new event - Creating calendar event:")
            new_event = GClient.create_event(event_name=round_name, start_time=tip_off, end_time=finish, attendees=ATTENDEES, location=venue, private_properties={"schedule":URL})
            print(f'Event [{new_event}] created for [{round_name}]')
