import helpers
import base64
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
import plotly as plotly
import chart_studio.plotly as py
import plotly.graph_objects as go
import plotly.io as pio
pio.renderers.default = "firefox"
pio.templates.default = "seaborn"

from jinja2 import Environment, FileSystemLoader

load_dotenv()

exclusions = os.getenv('EXCLUDE_CAT').split(',')
exclusions = [x.strip(' ') for x in exclusions]

chart_files = os.getenv('PLOTLY_filenames').split(',')
chart_files = [x.strip(' ') for x in chart_files]

hawk_mode = str(os.getenv('HAWK_MODE'))
print('Currently Running in {}'.format(hawk_mode))

tokens = helpers.plaidTokens()

start_of_month = helpers.monthStart()
chart_studio.tools.set_credentials_file(username=os.getenv('PLOTLY_USERNAME'), api_key=os.getenv('PLOTLY_API_KEY'))
clear_file = helpers.clear_data_file()
print(clear_file)

encoded = base64.b64encode(open('templates/logo.png', "rb").read())
#Data from Plaid
master_data = helpers.getData(hawk_mode, exclusions)
data = dict(
    date = date.today().strftime('%m/%d/%y'),
    balance_chase = master_data['balance_chase'],
    chase_total = master_data['chase_total'],
    balance_schwab = master_data['balance_schwab'],
    schwab_total = master_data['schwab_total'],
    balance_cap_one =  master_data['cap1_balance'],
    capone_total = master_data['cap1_total'],
    balance_great_lakes = master_data['lakes_balance'],
    greatlakes_total = master_data['lakes_total'],
    chart_pack = {},
    logo = 'data:image/png;base64,{}'.format(encoded.decode('utf8')),
    tables = []
)


chart_links = []
#Update Guage Chart
GC_link = helpers.guageChart(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)
chart_links.append(GC_link)
#Update Cumulative Chart
CS_link = helpers.cumulativeSum(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)
chart_links.append(CS_link)
# Update Monthly Spending Chart
both_frames, MS_link = helpers.monthlySpending(master_data['all_trnsx'], exclusions, hawk_mode, 'Yes')
chart_links.append(MS_link)

#Update this Month's Category Chart
CMC_link = helpers.curMonthCategories(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)
chart_links.append(CMC_link)
# HTML Tables for Most Spent Places in Top Categories
# TC_link = helpers.topCategoryName(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)
# print(TC_link)
TC_link = helpers.categorySubplots(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)
chart_links.append(TC_link)
#Update Category History Chart
catHistory_frame, CH_link = helpers.categoryHistory(master_data['all_trnsx'], exclusions, hawk_mode)
chart_links.append(CH_link)
#Update Relative Category Chart
RC_link = helpers.relativeCategories(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)
chart_links.append(RC_link)
#Table HTML
# pending_HTML = helpers.pendingTable(master_data['all_trnsx'], exclusions)
pay_table = helpers.payday(master_data['all_trnsx'], 'table')
posted_tbl, pending_tbl = helpers.transactionTables(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)
jumbo_tbl = helpers.jumboTable(master_data['all_trnsx'], start_of_month, exclusions, hawk_mode)

data['tables'].append(pay_table)
data['tables'].append(posted_tbl)
data['tables'].append(pending_tbl)
data['tables'].append(jumbo_tbl)

if hawk_mode == 'production' or hawk_mode == 'testing':
    chart_data = helpers.chartConvert(chart_links)
    data['chart_pack']['divs'] = chart_data
else:
    data['chart_pack']['divs'] = [GC_link, CS_link, CMC_link,  RC_link, MS_link, TC_link, CH_link]

mail_data = helpers.jinjaTEST(data, hawk_mode)
helpers.emailPreview(mail_data, hawk_mode)

if hawk_mode == 'sandbox' or hawk_mode == 'local_testing':
    binary = FirefoxBinary('/Applications/Firefox.app/Contents/MacOS/firefox-bin')
    browser = webdriver.Firefox(firefox_binary=binary, executable_path='/Users/jdb/.pyenv/versions/3.8.0/envs/hawkMailENV/bin/geckodriver')
    browser.get("file:///Users/jdb/Documents/Jeff/Apps/Finances/hawkMail/templates/email_preview.html")

else:
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




