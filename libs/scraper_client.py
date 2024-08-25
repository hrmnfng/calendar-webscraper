'''
This client is used to scrape and parse a HTML page given the following information:
'''

import requests

from helpers.html_parser import HTMLHelper
from loguru import logger

class ScraperClient:
    '''
    This is a class for scraping HTML content

    Attributes:
        name (str): Name of the class-object being created.

    Methods:
        get_html(self, address:str): Retrives the raw HTML content from a given page.
        scrape_events(self, html_content:str, parse_type:str): Scrape an html page and extract the relevant details.
    '''
    
    def __init__(self, name:str, default_timeout:int=30):
        self.name = name
        self.default_timeout = default_timeout
        logger.debug(f"Created scraper client object with name '{name}' with timeout set to '{default_timeout}'")


    @logger.catch
    def get_html(self, address:str):
        '''
        Retrives the raw HTML content from a given page.

        Args:
            address (str): The url string for the html page being scraped.

        Returns:
            The HTML content in string format

        '''
        logger.debug(f"Retrieving HTML content from '{address}'")
        response = requests.get(address, timeout=self.default_timeout)
        html_content = response.text

        return html_content


    @logger.catch
    def scrape_events(self, html_content:str, parse_type:str):
        '''
        Scrape an html page and extract the relevant details.

        Args:
            url (str): The url string for the html page being scraped.

        Returns:
            A dictionariy containing the events

        '''
        logger.debug(f"Attemping to scrape events using parse type '{parse_type}'")
        events_data = HTMLHelper.parse_html_content(html_content=html_content, parse_type=parse_type)

        return events_data
