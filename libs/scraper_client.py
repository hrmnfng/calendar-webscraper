'''
This client is used to scrape and parse a HTML page given the following information:
'''

import time

import requests

from helpers.html_parser import parse_html_content

class ScraperClient:
    '''
    This is a class for scraping HTML content

    Attributes:
        name (str): Name of the class-object being created.
        address (str): URL of the page being scraped

    Methods:
        get_html(self): Retrives the raw HTML content from a given page.
        scrape_events(self, html_content, parse_type): Scrape an html page and extract the relevant details.
    '''
    
    def __init__(self, name, url):
        self.name = name
        self.address = url
        print(f"Created object with name '{name}' and address '{url}'")

    def get_html(self):
        '''
        Retrives the raw HTML content from a given page.

        Args:
            url (str): The url string for the html page being scraped.

        Returns:
            The HTML content in string format

        '''
        response = requests.get(self.address, timeout=30)
        html_content = response.text

        return html_content

    def scrape_events(self, html_content:str, parse_type:str):
        '''
        Scrape an html page and extract the relevant details.

        Args:
            url (str): The url string for the html page being scraped.

        Returns:
            A dictionariy containing the events

        '''
        events_data = parse_html_content(html_content=html_content, parse_type=parse_type)

        return events_data

def test_query():
    time.sleep(5)
    return "test over"
