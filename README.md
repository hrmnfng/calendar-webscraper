# calendar-webscraper
This is a glorified Python script that scrapes HTML web pages and then creates calendar events from them.

There are clients that support both iCal and Google Calendar events, however the main implementation has been done with Google Calendar.

This scripts runs automatically every Monday morning at 6am via GitHub actions. It can be also be manually triggered in the workflows page, or run locally.

## Adding the created calendars to your personal Calendar

### Gmail
Please use the Calendar ID provided by Google e.g.
```
https://calendar.google.com/calendar/embed?src=hr54c8jfpgc8kp5o9fqkdolu4c%40group.calendar.google.com&ctz=Australia%2FSydney
```
1. Open the link
2. Click the `+` sign at the bottom right of screen to add the calendar to your Gmail account

### Outlook and others
Please use the .ics format for the calendar e.g.
```
https://calendar.google.com/calendar/ical/hr54c8jfpgc8kp5o9fqkdolu4c%40group.calendar.google.com/public/basic.ics
```
1. In Outlook, use the 'Add from internet' option

## Running this script yourself
Running this script yourself requires two components to be set:
1. Environment Variables
2. YAML Configuratoin files

### Setting Environment Variables
Before running this script, the following environment variables will need to be set:

| Env Variable | Use |
| --- | --- |
| GCAL_CLIENT_ID | - |
| GCAL_CLIENT_SECRET | - |
| GCAL_REFRESH_TOKEN | - |

Requires credential.json

### Setting the YAML Configration Files



