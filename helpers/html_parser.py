'''
Used parse different types of HTML pages and extracting the relevant information.
'''

from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import re
from loguru import logger

class HTMLHelper:

    @staticmethod
    @logger.catch
    def parse_html_content(html_content:str, parse_type:str, custom_parse:dict={}):
        '''
        Public method for parsing html content - will access private methods as required

        Args:
            html_content (str): The html content in string format that needs to be parsed.
            type (str): The specific parse method.
            custom_parse (dict): Optional param to speciy custom fields to parse.

        Returns:
            Private method for parsing differnt HTML pages.
        '''
        match parse_type:
            case "ssb":
                return HTMLHelper._parse_ssb_content(html_content)
            case "custom":
                return HTMLHelper._parse_custom_content(html_content, custom_parse)
            case other:
                logger.error("Invalid type passed in")

    @staticmethod
    @logger.catch
    def _parse_ssb_content(html_content):
        '''
        Parse the SSB page for date-time events for each game.

        Args:
            html_content (str): The html content in string format that needs to be parsed.

        Returns:
            Dict containing the time and date for every upcoming game

        '''
        logger.debug("Parsing SSB content")
        soup = BeautifulSoup(html_content, "html.parser")
        games = soup.find_all("div", class_="grid")
        game_schedules = []

        for element in games:
            #round = element.find("div", class_="cell").find("h5", text="Round").find_next_sibling(text=True).strip()
            game_round = element.find(string=re.compile("Round")).find_parent().find_next_sibling(text=True).strip()
            opponent = element.find(string=re.compile("Opponent")).find_next('a').get_text(strip=True)
            date = element.find(string=re.compile("Date")).find_parent().find_next_sibling(text=True).strip()
            time = element.find(string=re.compile("Time")).find_parent().find_next_sibling(text=True).strip()
            location = element.find(string=re.compile("Court")).find_parent().find_next_sibling(text=True).strip()
            details = element.find(string=re.compile("Score")).find_next('a', href=True).get("href")

            game_details = f"{game_round}: {opponent}"
            game_start = datetime.strptime((f"{date} {time}"), "%d/%m/%Y %I:%M%p") 
            game_end = game_start + timedelta(hours=1)
            game_schedules.append(
                {
                    "round": game_details, 
                    "start": game_start,
                    "end": game_end,
                    "location": location,
                    "details_url": details
                }
            )

        return game_schedules

    @staticmethod
    @logger.catch
    def _parse_custom_content(html_content:str, custom_parse:dict):
        '''
        Parse the SSB page for date-time events for each game.

        Args:
            html_content (str): The html content in string format that needs to be parsed.

        Returns:
            Dict containing the time and date for every upcoming game

        '''
        logger.debug("Parsing Custom content")
        soup = BeautifulSoup(html_content, "html.parser")
        
        return logger.warning("This hasn't been setup yet")
 