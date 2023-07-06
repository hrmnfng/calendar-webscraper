# calendar-webscraper
This is a glorified Python script that scrapes HTML web pages and then creates calendar events from them.

There are clients that support both iCal and Google Calendar events, however the main implementation has been done with Google Calendar.

This scripts runs automatically every Monday morning at 6am via GitHub actions. It can be also be manually triggered in the workflows page, or run locally.

## Running this script yourself
To run this script, the following environment variables will need to be set:

| Env Variable | Use |
| --- | --- |
| RECIPIENTS | The people to add to the calendar in a nested list format e.g. [{'email': 'person1@gmail.com'}, {'email': 'person2@gmail.com'}]. |
| SCHEDULE_URL | The URL for the game schedule e.g. https://sydneysocialbasketball.com.au/team/YOUR_TEAM_HERE/ |
| GCAL_CLIENT_ID | - |
| GCAL_CLIENT_SECRET | - |
| GCAL_REFRESH_TOKEN | - |

## Generating Google Client Credentails
:construction: TBD :construction:
