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


from jinja2 import Environment, FileSystemLoader

load_dotenv()

exclusions = os.getenv('EXCLUDE_CAT').split(',')
exclusions = [x.strip(' ') for x in exclusions]


hawk_mode = str(os.getenv('HAWK_MODE'))
print('Currently Running in {}'.format(hawk_mode))
print('exclusions: ', type(exclusions))
print(exclusions)
tokens = helpers.plaidTokens()
today_str = str(date.today())
start_of_month = helpers.monthStart()

clear_file = helpers.clear_data_file()
print(clear_file)

if hawk_mode == 'sandbox':
    start_date = date.today().replace(year = date.today().year - 2).strftime('%Y-%m-%d')
    trnsx_chase, balance_chase = helpers.getTransactions(helpers.SANDBOXplaidClient(), tokens['Chase']['sandbox'], start_date, today_str)
    trnsx_schwab, balance_schwab = helpers.getTransactions(helpers.SANDBOXplaidClient(), tokens['Schwab']['sandbox'], start_date, today_str)
    cap1_response = helpers.cap1_lakes_get(helpers.SANDBOXplaidClient(), tokens['Capital_One']['sandbox'], start_of_month, today_str)
    lakes_response = helpers.cap1_lakes_get(helpers.SANDBOXplaidClient(), tokens['Great_Lakes']['sandbox'], start_of_month, today_str)

elif hawk_mode == 'testing':
    start_date = date.today() - timedelta(days=7)
    trnsx_chase, balance_chase = helpers.getTransactions(helpers.plaidClient(), tokens['Chase']['access_token'], start_date.strftime('%Y-%m-%d'), today_str)
    trnsx_schwab, balance_schwab = helpers.getTransactions(helpers.plaidClient(), tokens['Schwab']['access_token'], start_date.strftime('%Y-%m-%d'), today_str)
    cap1_response = helpers.cap1_lakes_get(helpers.plaidClient(), tokens['Capital_One']['access_token'], start_of_month, today_str)
    lakes_response = helpers.cap1_lakes_get(helpers.plaidClient(), tokens['Great_Lakes']['access_token'], start_of_month, today_str)


elif hawk_mode == 'production':
    start_date = date.today().replace(year = date.today().year - 2).strftime('%Y-%m-%d')
    trnsx_chase, balance_chase = helpers.getTransactions(helpers.plaidClient(), tokens['Chase']['access_token'], start_date, today_str)
    trnsx_schwab, balance_schwab = helpers.getTransactions(helpers.plaidClient(), tokens['Schwab']['access_token'], start_date, today_str)
    cap1_response = helpers.cap1_lakes_get(helpers.plaidClient(), tokens['Capital_One']['access_token'], start_of_month, today_str)
    lakes_response = helpers.cap1_lakes_get(helpers.plaidClient(), tokens['Great_Lakes']['access_token'], start_of_month, today_str)

try:
    chase_total = helpers.pandaSum(helpers.json2pandaClean(trnsx_chase, exclusions))
    schwab_total = helpers.pandaSum(helpers.json2pandaClean(trnsx_schwab, exclusions))
    lakes_balance, lakes_total = helpers.lakesData(lakes_response)
    cap1_balance, cap1_total = helpers.lakesData(cap1_response)
    all_trnsx = trnsx_chase + trnsx_schwab

except Exception as e:
    print(e)
    chase_total = 0
    schwab_total = 0
    cap1_total = 0
    lakes_total = 0
    all_trnsx = {'error': 'error'}

ms_frame = helpers.monthlySpending(all_trnsx, exclusions, start_of_month)
rez = helpers.plotlyMonthlyChart(ms_frame)
print(rez)

prog_pct = helpers.progress(all_trnsx, start_of_month, exclusions)

cat_spend_cur_month = helpers.curMonthCategories(all_trnsx, start_of_month, exclusions)
rez = helpers.plotlyCategoryChart_Update(cat_spend_cur_month)
print(rez)

cat_spend_all = helpers.categoryHistory(all_trnsx, exclusions)
rez = helpers.plotlyCategoryHistory_Update(cat_spend_all)
print(rez)

cumulative_spending = helpers.cumulativeSum(all_trnsx, start_of_month, exclusions)
rez = helpers.cumSpendChart_Update(cumulative_spending)
print(rez)

pending_frame = helpers.pendingTable(all_trnsx)
rez = helpers.plotlyPtable(pending_frame)
print(rez)

cur_month_transaction_table = helpers.monthsTransactionTable(all_trnsx, start_of_month)
helpers.plotlyTtable(cur_month_transaction_table)

charts_html = helpers.htmlGraph(os.getenv('PLOTLY_GRAPHS').split(","))

charts_and_tables_html = helpers.htmlTable(os.getenv('PLOTLY_TABLES').split(","), charts_html)



mail_data = helpers.generate_HTML(balance_chase, balance_schwab, charts_and_tables_html, chase_total, schwab_total, cap1_total, lakes_total, lakes_balance, cap1_balance)
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
        print(response.status_code)
        print(response.body)
        print(response.headers)
    except Exception as e:
        print(str(e))

else:

    binary = FirefoxBinary('/Applications/Firefox.app/Contents/MacOS/firefox-bin')
    browser = webdriver.Firefox(firefox_binary=binary, executable_path='/Users/jdb/.pyenv/versions/3.8.0/envs/hawkMailENV/bin/geckodriver')
    browser.get("file:///Users/jdb/Documents/Jeff/Apps/Finances/hawkMail/templates/email_preview.html")

