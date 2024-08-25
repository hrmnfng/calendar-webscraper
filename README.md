# calendar-webscraper [![Schedule to Calendar](https://github.com/hrmnfng/calendar-webscraper/actions/workflows/execute-script.yml/badge.svg?branch=main)](https://github.com/hrmnfng/calendar-webscraper/actions/workflows/execute-script.yml)

This is a glorified Python script that scrapes HTML web pages and then creates calendar events from them.

There are clients that support both iCal and Google Calendar events, however the main implementation has been done with Google Calendar.

This scripts runs automatically every morning at 6am via GitHub Actions. It can be also be manually triggered in the workflows page, or run locally.

## Adding the created calendars to your personal calendar

Please see the [pinned issue](https://github.com/hrmnfng/calendar-webscraper/issues/13) in this GitHub repository for the links to the available calendars. This issue will be updated as necesssary whenever a new schedule is added.

## Running this script yourself

Running this script yourself requires two components to be set:

1. Environment Variables
2. YAML Configuration files

You can then run the script via the following python commands:

```shell
pipenv install -r ./requirements.txt

pipenv run create_gcal_events.py
```

### Setting environment variables

Before running this script, the following environment variables will need to be set:

| Env Variable       | Use                                                                                                      |
| ------------------ | -------------------------------------------------------------------------------------------------------- |
| GCAL_CLIENT_ID     | The unique identifier assigned to an application/client that's attempting to access Google's APIs        |
| GCAL_CLIENT_SECRET | A confidential value associated with the client ID that is used for authentication                       |
| GCAL_REFRESH_TOKEN | A long-lived credential that allows the application to obtain new access tokens without user involvement |
| LOG_LEVEL          | The log level the application - default is "INFO"                                                        |

### Local Setup

<br>
<details>

<summary>Instructions for generating the values for these environment variables locally</summary>

1. Clone down this repository
2. If you don't have one already, create a new project in the Google Cloud console (you may need to sign up - note that Refresh tokens for projects with "Publishing Status" set to `Testing` will expire in 7 days)
3. In that project, navigate to `APIs & Services` > `Credentials` in the left hand menu
4. Generate a new `OAuth Client ID` by clicking on `CREATE CREDENTIALS` in the top bar
    1. Set the Application Type to `Desktop app`
    2. Set the name to whatever you'd like
    3. Click `CREATE` button to proceed
5. When the dialogue box confirming credential creation appears, click on the `DOWNLOAD.JSON`button at the bottom
6. Rename this file to `credentials.json` and add it to the root directory of this repository
7. Run `libs\google_cal_client.py` directly to generate your token credentials (you may uncomment out the print statements at the bottom for easier access)
8. Once you have saved these values as the above environment variables, you are free to delete the `credentials.json` file

</details>
<br>

Reminder that these environment variables are all sensitive credentials that can be used to grant access to Google account associated with the Google Cloud console project. 

### Setting up the YAML configration files

This script uses YAML configuration files to determine which calendars to create and what events to populate them with.

These files are stored in the `calendar-configs` folder in the root directory, and are read at runtime. There is a template file (`calendar-configs/_config_template.yaml`) that outlines what information the files should contain.

Please note that even after these calendars are created, they need to be manually set to public and relevant URLs shared. Currently, there is no way to do this via Google's APIs.
