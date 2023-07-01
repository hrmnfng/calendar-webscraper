import pprint

from helpers.decorator import func_default_wrapper, func_timer
from libs.scraper_client import ScraperClient, test_query
from libs.ical_client import iCalClient


# create the scraper client and scrape
dummyScraper = ScraperClient("SSB_test", "https://sydneysocialbasketball.com.au/team/shake-shaq-6/")

html_content = dummyScraper.get_html()
game_data = dummyScraper.scrape_events(html_content=html_content, parse_type="ssb")

# print results
pprint.pprint(game_data)

calClient = iCalClient("Ical Client")

for game in game_data:
    round_name = game["round"]
    tip_off = game["time"]
    location = game["location"]

    calClient.add_event(event_name=round_name, event_time=tip_off, event_location=location)

ical_data = calClient.generate_ical_data()
pprint.pprint(ical_data)