import helpers
import plaid
from plaid.errors import APIError, ItemError
import requests
import json
from plaid import Client
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

exclusions = os.getenv('EXCLUDE_CAT').split(",")

# temp = helpers.jinjaTEST('11', '12')
# print(temp)
tokens = helpers.plaidTokens()
today_str = str(date.today())
start_of_month = helpers.monthStart()


# TESTING
# trnsx_chase, balance_chase = helpers.TEST_getTransactions(tokens['Chase']['access_token'], today_str)
# trnsx_schwab, balance_schwab = helpers.TEST_getTransactions(tokens['Schwab']['access_token'], today_str)

#Production
trnsx_chase, balance_chase = helpers.getTransactions(tokens['Chase']['access_token'], today_str)
trnsx_schwab, balance_schwab = helpers.getTransactions(tokens['Schwab']['access_token'], today_str)
trnsx_great_lakes, balance_great_lakes = helpers.getTransactions(tokens['Great_Lakes']['access_token'], today_str)
trnsx_cap_one, balance_cap_one = helpers.getTransactions(tokens['Capital_One']['access_token'], today_str)

chase_total = helpers.pandaSum(helpers.json2pandaClean(trnsx_chase, exclusions))
schwab_total = helpers.pandaSum(helpers.json2pandaClean(trnsx_schwab, exclusions))

try:
    all_trnsx = trnsx_chase + trnsx_schwab
except:
    all_trnsx = trnsx_chase

ms_frame = helpers.monthlySpending(all_trnsx, exclusions)
helpers.plotlyMonthlyChart(ms_frame)

prog_pct = helpers.progress(all_trnsx, start_of_month, exclusions)

cat_spend_cur_month = helpers.curMonthCategories(all_trnsx, start_of_month, exclusions)
helpers.plotlyCategoryChart_Update(cat_spend_cur_month)

cat_spend_all = helpers.categoryHistory(all_trnsx, exclusions)
helpers.plotlyCategoryHistory_Update(cat_spend_all)

cumulative_spending = helpers.cumulativeSum(all_trnsx, start_of_month, exclusions)
helpers.cumSpendChart_Update(cumulative_spending)

pending_frame = helpers.pendingTable(all_trnsx)
helpers.plotlyPtable(pending_frame)

cur_month_transaction_table = helpers.monthsTransactionTable(all_trnsx, start_of_month)
helpers.plotlyTtable(cur_month_transaction_table)

charts_html = helpers.htmlGraph(os.getenv('PLOTLY_GRAPHS').split(","))

charts_and_tables_html = helpers.htmlTable(os.getenv('PLOTLY_TABLES').split(","), charts_html)



#print(html)
mail_data = helpers.generate_HTML(balance_chase, balance_schwab, charts_and_tables_html, chase_total, schwab_total, balance_great_lakes, balance_cap_one)
helpers.emailPreview(mail_data)

with open('templates/email_preview.html', 'r') as f:
    html_string = f.read()


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

