from __future__ import print_function
from bs4 import BeautifulSoup
from urllib.request import urlopen
from datetime import date
import re
import numpy as np
import pandas as pd
import pickle
import threading
import sys
from tika import parser
import requests

class FOMC (object):
    '''
    A convenient class for extracting meeting minutes from the FOMC website
    Example Usage:  
        fomc = FOMC()
        df = fomc.get_statements()
        fomc.pickle("./df_minutes.pickle")
    '''

    def __init__(self, content_type = 'statement',
                 base_url='https://www.federalreserve.gov', 
                 calendar_url='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm',
                 speech_base_url='https://www.federalreserve.gov/newsevents/speech',
                 historical_date_statement = 2014,
                 historical_date_speech = 2010,
                 verbose = True,
                 max_threads = 10,
                 base_dir = '../data/FOMC/'):

        self.content_type = content_type
        self.base_url = base_url
        self.calendar_url = calendar_url
        self.speech_base_url = speech_base_url
        self.df = None
        self.links = None
        self.dates = None
        self.articles = None
        self.speaker = None
        self.verbose = verbose
        self.HISTORICAL_DATE_STATEMENT = historical_date_statement
        self.HISTORICAL_DATE_SPEECH = historical_date_speech
        self.MAX_THREADS = max_threads
        self.base_dir = base_dir

    def _get_links(self, from_year):
        '''
        private function that sets all the links for the FOMC meetings
         from the giving from_year to the current most recent year
         from_year is min(2015, from_year)

        '''
        self.links = []
        fomc_meetings_socket = urlopen(self.calendar_url)
        soup = BeautifulSoup(fomc_meetings_socket, 'html.parser')

        if self.content_type in ('statement', 'minutes', 'script'):
            if self.content_type == 'statement':
                if self.verbose: print("Getting links for statements...")
                contents = soup.find_all('a', href=re.compile('^/newsevents/pressreleases/monetary\d{8}[ax].htm'))
                self.links = [content.attrs['href'] for content in contents]
                if self.verbose: print("{} links found in the current page.".format(len(self.links)))
            elif self.content_type == 'minutes':
                if self.verbose: print("Getting links for minutes...")
                contents = soup.find_all('a', href=re.compile('^/monetarypolicy/fomcminutes\d{8}.htm'))
                self.links = [content.attrs['href'] for content in contents]
                if self.verbose: print("{} links found in the current page.".format(len(self.links)))
            elif self.content_type == 'script':
                if self.verbose: print("Getting links for press conference scripts...")
                presconfs = soup.find_all('a', href=re.compile('^/monetarypolicy/fomcpresconf\d{8}.htm'))
                presconf_urls = [self.base_url + presconf.attrs['href'] for presconf in presconfs]
                for presconf_url in presconf_urls:
                    # print(presconf_url)
                    presconf_socket = urlopen(presconf_url)
                    soup_presconf = BeautifulSoup(presconf_socket, 'html.parser')
                    contents = soup_presconf.find_all('a', href=re.compile('^/mediacenter/files/FOMCpresconf\d{8}.pdf'))
                    for content in contents:
                        #print(content)
                        self.links.append(content.attrs['href'])

            if from_year <= self.HISTORICAL_DATE_STATEMENT:
                for year in range(from_year, self.HISTORICAL_DATE_STATEMENT + 1):
                    fomc_yearly_url = self.base_url + '/monetarypolicy/fomchistorical' + str(year) + '.htm'
                    fomc_yearly_socket = urlopen(fomc_yearly_url)
                    soup_yearly = BeautifulSoup(fomc_yearly_socket, 'html.parser')
                    if self.content_type == 'statement':
                        yearly_pages = soup_yearly.findAll('a', text = 'Statement')
                    elif self.content_type == 'minutes':
                        yearly_pages = soup_yearly.find_all('a', href=re.compile('(^/monetarypolicy/fomcminutes|^/fomc/minutes|^/fomc/MINUTES)'))
                    elif self.content_type == 'script':
                        yearly_pages = soup_yearly.find_all('a', href=re.compile('^/monetarypolicy/files/FOMC\d{8}meeting.pdf'))
                    
                    for yearly_page in yearly_pages:
                        self.links.append(yearly_page.attrs['href'])
                    if self.verbose: print("YEAR: {} - {} links found.".format(year, len(yearly_pages)))

            print("There are total ", len(self.links), ' links for ', self.content_type)
        elif self.content_type == 'speech':
            if self.verbose: print("Getting links for speeches...")
            self.links = []
            to_year = date.today().strftime("%Y")
            if from_year < 1996:
                print("Archive only exist up to 1996, so setting from_year as 1996...")
                from_year = 1996
            if from_year <= self.HISTORICAL_DATE_SPEECH:
                for year in range(from_year, self.HISTORICAL_DATE_SPEECH+1):
                    fomc_speeches_yearly_url = self.speech_base_url + '/' + str(year) + 'speech.htm'
                    # print(fomc_speeches_yearly_url)
                    fomc_speeches_yearly_socket = urlopen(fomc_speeches_yearly_url)
                    soup_speeches_yearly = BeautifulSoup(fomc_speeches_yearly_socket, 'html.parser')
                    speeches_historical = soup_speeches_yearly.findAll('a', href=re.compile('^/newsevents/speech/.*\d{8}.*.htm|^/boarddocs/speeches/\d{4}/|d{8}.*.htm'))
                    for speech_historical in speeches_historical:
                        self.links.append(speech_historical.attrs['href'])
                    if self.verbose: print("YEAR: {} - {} speeches found.".format(year, len(speeches_historical)))
                from_year = self.HISTORICAL_DATE_SPEECH+1
            from_year = np.max([from_year, self.HISTORICAL_DATE_SPEECH+1])
            for year in range(from_year, int(to_year)+1):
                fomc_speeches_yearly_url = self.speech_base_url + '/' + str(year) + '-speeches.htm'
                fomc_speeches_yearly_socket = urlopen(fomc_speeches_yearly_url)
                soup_speeches_yearly = BeautifulSoup(fomc_speeches_yearly_socket, 'html.parser')
                speeches_historical = soup_speeches_yearly.findAll('a', href=re.compile('newsevents/speech/.*\d{8}.*.htm'))
                for speech_historical in speeches_historical:
                    self.links.append(speech_historical.attrs['href'])
                if self.verbose:
                    print("YEAR: {} - {} speeches found.".format(year, len(speeches_historical)))
        else:
            print("Wrong Content Type")

    def _date_from_link(self, link):
        print(link)
        date = re.findall('[0-9]{8}', link)[0]
        if date[4] == '0':
            date = "{}/{}/{}".format(date[:4], date[5:6], date[6:])
        else:
            date = "{}/{}/{}".format(date[:4], date[4:6], date[6:])
        return date

    def _speaker_from_link(self, link):
        speaker_search = re.search('newsevents/speech/(.*)\d{8}(.*)', link)
        if speaker_search:
            speaker = speaker_search.group(1)
        else:
            speaker = "None"
        return speaker

    def _pdf_to_text(self, link):
        pdf_socket = urlopen

    def _add_article(self, link, index=None):
        '''
        adds the related article for 1 link into the instance variable
        index is the index in the article to add to. Due to concurrent
        prcessing, we need to make sure the articles are stored in the
        right order
        '''
        if self.verbose:
            sys.stdout.write(".")
            sys.stdout.flush()

        link_url = self.base_url + link
        article_date = self._date_from_link(link)

        # date of the article content
        self.dates.append(article_date)
        if self.content_type == 'speech':
            self.speaker.append(self._speaker_from_link(link))

        if self.content_type == 'script':
            res = requests.get(link_url)
            pdf_filepath = self.base_dir + 'script_pdf/FOMC_PresConfScript_' + article_date.replace('/', '-') + '.pdf'
            with open(pdf_filepath, 'wb') as f:
                f.write(res.content)
            pdf_file_parsed = parser.from_file(pdf_filepath)
            self.articles[index] = pdf_file_parsed['content'].strip()
        else:
            article_socket = urlopen(self.base_url + link)
            article = BeautifulSoup(article_socket, 'html.parser')
            paragraphs = article.findAll('p')
            self.articles[index]= "\n\n".join([paragraph.get_text().strip() for paragraph in paragraphs])

    def _get_articles_multi_threaded(self):
        '''
        gets all articles using multi-threading
        '''
        if self.verbose:
            print("Getting articles - Multi-threaded...")

        self.dates, self.speaker, self.articles = [], [], ['']*len(self.links)
        jobs = []
        # initiate and start threads:
        index = 0
        while index < len(self.links):
            if len(jobs) < self.MAX_THREADS:
                t = threading.Thread(target=self._add_article, args=(self.links[index],index,))
                jobs.append(t)
                t.start()
                index += 1
            else:    # wait for threads to complete and join them back into the main thread
                t = jobs.pop(0)
                t.join()
        for t in jobs:
            t.join()

        for row in range(len(self.articles)):
            self.articles[row] = self.articles[row].strip()

    def get_contents(self, from_year=1990):
        '''
        Returns a Pandas DataFrame with the date as the index
        uses a date range of from_year to the most current
        '''
        self._get_links(from_year)
        self._get_articles_multi_threaded()
        self.df = pd.DataFrame(self.articles, index=pd.to_datetime(self.dates)).sort_index()
        self.df.columns = ['contents']
        if self.content_type == 'speech':
            self.df.speaker = self.speaker
        return self.df

    def pickle_dump_df(self, filename="output.pickle"):
        filepath = self.base_dir + filename
        if self.verbose: print("Writing to ", filepath)
        with open(filepath, "wb") as output_file:
            pickle.dump(self.df, output_file)

    def save_texts(self, prefix="FOMC_", target="contents"):
        for i in range(self.df.shape[0]):
            if self.content_type == 'speech':
                filepath = self.base_dir + prefix + self.df.index.strftime('%Y-%m-%d')[i] + '_' + self.df.speaker[i] + ".txt"
            else:
                filepath = self.base_dir + prefix + self.df.index.strftime('%Y-%m-%d')[i] + ".txt"
            if self.verbose: print("Writing to ", filepath)
            with open(filepath, "w") as output_file:
                output_file.write(self.df.iloc[i][target])

if __name__ == '__main__':
    pg_name = sys.argv[0]
    args = sys.argv[1:]
    
    if len(sys.argv) != 2:
        print("Usage: ", pg_name)
        print("Please specify ONE argument from ('statement', 'minutes', 'script', 'speech')")
        sys.exit(1)
    if args[0].lower() not in ('statement', 'minutes', 'script', 'speech'):
        print("Usage: ", pg_name)
        print("Please specify ONE argument from ('statement', 'minutes', 'script', 'speech')")
        sys.exit(1)
    else:
        fomc = FOMC(content_type=args[0])
        df = fomc.get_contents(1990)
        fomc.pickle_dump_df(filename = fomc.content_type + ".pickle")
        fomc.save_texts(prefix = fomc.content_type + "/FOMC_" + fomc.content_type + "_")