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
load_dotenv()

EXCLUDE_CAT = ['18020004', '16001000', '21009000', '21005000', '21009000', '21006000', '21007000', '18063000']

def plaidClient():
    client = plaid.Client(os.getenv('PLAID_CLIENT_ID'),
                          os.getenv('PLAID_SECRET'),
                          os.getenv('PLAID_PUBLIC_KEY'),
                          os.getenv('PLAID_ENV'),
                          api_version='2018-05-22')
    return client

def plaidTokens():
    tokens = {}
    tokens['Chase'] = {'access_token': os.getenv('ACCESS_TOKEN_Chase'), 'item_id': os.getenv('ITEM_ID_Chase'), 'id': 1}
    tokens['Schwab'] = {'access_token': os.getenv('ACCESS_TOKEN_Schwab'), 'item_id': os.getenv('ITEM_ID_Schwab'), 'id': 2}
    tokens['Great_Lakes'] = {'access_token': os.getenv('ACCESS_TOKEN_Lakes'), 'item_id': os.getenv('ITEM_ID_Lakes'), 'id': 3}
    tokens['Capital_One'] = {'access_token': os.getenv('ACCESS_TOKEN_Cap1'), 'item_id': os.getenv('ITEM_ID_Cap1'), 'id': 4}
    return tokens


client = plaidClient()
tokens = plaidTokens()
print(client)

print('***Dates***')
today_str = str(date.today())
today = date.today()
print("Today's Date: ", today)
yesterday = str(date.today() + timedelta(-1))
print("Yesterday: ", yesterday)
start_date = "2016-01-01"
print("Start of History: ", start_date)

todayDate = date.today()
if todayDate.day > 25:
    todayDate += timedelta(7)
month_start = str(todayDate.replace(day=1))
print('Month Start Date: ', month_start)






account_ids = [account['account_id'] for account in client.Accounts.get(tokens['Chase']['access_token'])['accounts']]
print("paginating...")
num_available_transactions = client.Transactions.get(tokens['Chase']['access_token'], start_date, today, account_ids=account_ids)['total_transactions']
print("Transactions from Plaid: ", num_available_transactions)
num_pages = math.ceil(num_available_transactions / 500)
print("Pages: ", num_pages)
transactions = []

for page_num in range(num_pages):
    transactions += [transaction for transaction in client.Transactions.get(tokens['Chase']['access_token'], start_date, today, account_ids=account_ids, offset=page_num * 500, count=500)['transactions']]

print("Transactions from Plaid: ", transactions[0])

jload = {}
jload['transactions'] = transactions


#Spent this Month#
df = json_normalize(jload, 'transactions')
df["date"] = pd.to_datetime(df['date'])
df = df[~df['category_id'].isin(EXCLUDE_CAT)]
df = df.set_index('date')
#Spent Yesterday#
pending = df.loc[df.pending == True]['amount'].sum()

print("Pending Transactions: ", pending)
df = df.loc[df.pending == False]
spent_yesterday = df.loc[df.index >= yesterday]['amount'].sum()
print("Yesterday's Spend: ", spent_yesterday)
spent_this_month = df[:month_start]['amount'].sum()
print("This Month's Spend: ", spent_this_month)

monthly_sum = df.resample('M')['amount'].sum()
print('Sum By Month')
print(monthly_sum)

ave_months = monthly_sum.groupby(monthly_sum.index.month).mean()
datem = today.month
ave_4_this_month = ave_months[datem]

percent = spent_this_month/ave_4_this_month
print("Percent of Average for this Month: ", percent)
#Category Totals Each Month#

for a in jload['transactions']:
    if a['category'] is not None:
        a['category'] = a["category"][-1]
cat_df = json_normalize(jload, 'transactions')
cat_df = cat_df[~cat_df['category_id'].isin(EXCLUDE_CAT)]
cat_df["date"] = pd.to_datetime(cat_df['date'])
cat_df = cat_df.set_index('date')
cat_df = cat_df[:month_start]
cat_df = cat_df.groupby('category')["amount"].resample("M").sum()

print('Category Spend: ', cat_df)
df_fram = cat_df.to_frame()
cat_html = df_fram.to_html()

month_trnsx = df.loc[df.index >= month_start]
monthly_html = month_trnsx.to_html()

html = ''
html += '<!DOCTYPE html><html lang="en"><head>SAR Leaver Found! </head><body><div class="card is-centered pie-chart-card"><span class="badge mantis">Good</span><div class="pie-chart">'
html +=  '<div class="pie-chart-svg">'
html +=   '<svg width="100%" height="100%" viewBox="0 0 42 42" class="donut">'
html +=    '<circle class="donut-hole" cx="21" cy="21" r="15.91549430918954" fill="#fff"></circle>'
html +=   '<circle class="donut-ring" cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#9e9e9e" stroke-width="2"></circle>'
html +=  '<circle class="donut-segment" cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#18c96e" stroke-width="2" stroke-dasharray="60 40" stroke-dashoffset="0"></circle>'
html += '<circle class="donut-segment" cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#b71c1c" stroke-width="2" stroke-dasharray="20 80" stroke-dashoffset="45"></circle>'
html +='<circle class="donut-segment" cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#9e9e9e" stroke-width="2" stroke-dasharray="25 75" stroke-dashoffset="25"></circle>'
html +='</svg>'
html += '<span class="pie-chart-number is-size-h2">'
html += str(spent_yesterday)
html +='%</span>'
html += '</div><ul class="pie-chart-legend"><li><span class="label label-delivered">Spent Yesterday</span></li><li></ul></div><span class="has-underline is-size-h2" data-tooltip="Tooltip down!" data-tooltip-pos="down">Spending</span></div>'
html += '<div class="card is-centered pie-chart-card"><span class="badge mantis">Good</span><div class="pie-chart"><div class="pie-chart-svg"><svg width="100%" height="100%" viewBox="0 0 42 42" class="donut">'
html +=    '<circle class="donut-hole" cx="21" cy="21" r="15.91549430918954" fill="#fff"></circle>'
html +=   '<circle class="donut-ring" cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#9e9e9e" stroke-width="2"></circle>'
html +=  '<circle class="donut-segment" cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#18c96e" stroke-width="2" stroke-dasharray="60 40" stroke-dashoffset="0"></circle>'
html +=    '<circle class="donut-segment" cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#b71c1c" stroke-width="2" stroke-dasharray="20 80" stroke-dashoffset="45"></circle>'
html +=   '<circle class="donut-segment" cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#9e9e9e" stroke-width="2" stroke-dasharray="25 75" stroke-dashoffset="25"></circle>'
html +=  '</svg><span class="pie-chart-number is-size-h2">'
html += str(percent)
html += '%</span></div><ul class="pie-chart-legend"><li><span class="label label-delivered">Percent of Average this Month</span></li></ul></div>'
html += '<span class="has-underline is-size-h2" data-tooltip="Tooltip down!" data-tooltip-pos="down">Spending: '
html += str(spent_this_month)
html += '</span></div><div class="stats-card"><div class="card-stat"><p class="stat">$'
html += str(pending)
html += '</p><p class="label">Pending Transactions</p></div></div><div>'
html += str(cat_html)
html += '</div><div>'
html += str(monthly_html)
html += '</div></body></html>'

print(html)

message = Mail(
    from_email=os.getenv('SENDGRID_MAIL'),
    to_emails=os.getenv('SENDGRID_MAIL'),
    subject='Daily Spending Report',
    html_content=html)
try:
    sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
    response = sg.send(message)
    print(response.status_code)
    print(response.body)
    print(response.headers)
except Exception as e:
    print(str(e))

