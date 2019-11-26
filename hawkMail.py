import helpers
import plaid
from plaid.errors import APIError, ItemError
import requests
import json
from plaid import Client
from selenium import webdriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
import os
import math
from datetime import datetime, timedelta, date
import pandas as pd
from pandas.io.json import json_normalize
from dotenv import load_dotenv
import sendgrid
import os
from sendgrid.helpers.mail import Mail
from sendgrid import SendGridAPIClient
import python_http_client

import chart_studio
import plotly
import chart_studio.plotly as py
import plotly.graph_objects as go
import plotly.io as pio
pio.renderers.default = "firefox"


from jinja2 import Environment, FileSystemLoader

load_dotenv()

exclusions = os.getenv('EXCLUDE_CAT').split(',')
exclusions = [x.strip(' ') for x in exclusions]

chart_files = os.getenv('PLOTLY_filenames').split(',')
chart_files = [x.strip(' ') for x in chart_files]

hawk_mode = str(os.getenv('HAWK_MODE'))
print('Currently Running in {}'.format(hawk_mode))
print('exclusions: ', type(exclusions))
print(exclusions)
print('chart files: ', type(chart_files))
print(chart_files)
tokens = helpers.plaidTokens()

start_of_month = helpers.monthStart()
chart_studio.tools.set_credentials_file(username=os.getenv('PLOTLY_USERNAME'), api_key=os.getenv('PLOTLY_API_KEY'))
clear_file = helpers.clear_data_file()
print(clear_file)

#Data from Plaid
master_data = helpers.getData(hawk_mode, exclusions)
data = dict(
    date=date.today().strftime('%m/%d/%y'),
    balance_chase=master_data['balance_chase'],
    chase_total=master_data['chase_total'],
    balance_schwab=master_data['balance_schwab'],
    schwab_total= master_data['schwab_total'],
    balance_cap_one=  master_data['cap1_balance'],
    capone_total='<BETA>',
    balance_great_lakes=master_data['lakes_balance'],
    greatlakes_total='<BETA>',
    chart_pack = {}
)


#Update Cumulative Chart
rez = helpers.cumulativeSum(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)
print(rez)

# Update Monthly Spending Chart
rez = helpers.monthlySpending(master_data['all_trnsx'], exclusions, hawk_mode)
print(rez)

#Update 3 Month Average Comparison Number
prog_pct = helpers.progress(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)
print(prog_pct)
#Update this Month's Category Chart
rez = helpers.curMonthCategories(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)
print(rez)

# HTML Tables for Most Spent Places in Top Categories
topCatHTML = helpers.topCategoryName(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)


#Update Category History Chart
rez = helpers.categoryHistory(master_data['all_trnsx'], exclusions, hawk_mode)
print(rez)

#Update Relative Category Chart
rez = helpers.relativeCategories(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)
print(rez)

#Table HTML
pending_HTML = helpers.pendingTable(master_data['all_trnsx'], exclusions)
transaction_HTML = helpers.monthsTransactionTable(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)


#charts_html = helpers.htmlGraph(os.getenv('PLOTLY_GRAPHS').split(","))

#charts_and_tables_html = helpers.htmlTable(os.getenv('PLOTLY_TABLES').split(","), charts_html)



# mail_data = helpers.generate_HTML(balance_chase, balance_schwab, charts_and_tables_html,\
#                                  chase_total, schwab_total, cap1_total, \
#
#                                  lakes_balance, cap1_balance, topCatHTML)


data['chart_pack']['chartHTML'] = helpers.tableChartHTML(master_data['all_trnsx'], month_start, exclusions, hawk_mode, chart_files)
pending = helpers.pendingTable(master_data['all_trnsx'], exclusions)
months = helpers.monthsTransactionTable(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)
data['chart_pack']['tableHTML'] = pending + months

# print('ChartHTML: ', data['chart_pack']['chartHTML'])

mail_data = helpers.jinjaTEST(data)
helpers.emailPreview(mail_data)



if hawk_mode == 'production' or hawk_mode == 'testing':
    with open('templates/email_preview.html', 'r') as f:
        html_string = f.read()
        f.close()

    message = Mail(
        from_email=os.getenv('SENDGRID_MAIL'),
        to_emails=os.getenv('SENDGRID_MAIL'),
        subject='Daily Spending Report',
        html_content=html_string)
    try:
        sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        response = sg.send(message)
        print('>>> Send Grid Response Data')
        print(response.status_code)
        print(response.body)
        print(response.headers)
    except Exception as e:
        print('>>> SendGrid ERROR')
        print(str(e))

else:

    binary = FirefoxBinary('/Applications/Firefox.app/Contents/MacOS/firefox-bin')
    browser = webdriver.Firefox(firefox_binary=binary, executable_path='/Users/jdb/.pyenv/versions/3.8.0/envs/hawkMailENV/bin/geckodriver')
    browser.get("file:///Users/jdb/Documents/Jeff/Apps/Finances/hawkMail/templates/email_preview.html")

