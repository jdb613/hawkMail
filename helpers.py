from flatten_json import flatten
import pandas as pd
from datetime import datetime, timedelta, date
import chart_studio.plotly as py
import plotly.graph_objects as go
import chart_studio
import plaid
from plaid.errors import APIError, ItemError
import requests
import json
from plaid import Client
from jinja2 import Environment, FileSystemLoader
import os

today_str = str(date.today())

chart_studio.tools.set_credentials_file(username=os.getenv('PLOTLY_USERNAME'), api_key=os.getenv('PLOTLY_API_KEY'))

def plaidClient():
    client = plaid.Client(os.getenv('PLAID_CLIENT_ID'),
                          os.getenv('PLAID_SECRET'),
                          os.getenv('PLAID_PUBLIC_KEY'),
                          os.getenv('PLAID_ENV'),
                          api_version='2018-05-22')

def TESTplaidClient():
    client = plaid.Client(os.getenv('PLAID_CLIENT_ID'),
                        os.getenv('PLAID_SECRET'),
                        os.getenv('PLAID_PUBLIC_KEY'),
                        os.getenv('TEST_PLAID_ENV'),
                        api_version='2018-05-22')
    return client

def plaidTokens():
    tokens = {}
    tokens['Chase'] = {'access_token': os.getenv('ACCESS_TOKEN_Chase'), 'item_id': os.getenv('ITEM_ID_Chase'), 'id': 1}
    tokens['Schwab'] = {'access_token': os.getenv('ACCESS_TOKEN_Schwab'), 'item_id': os.getenv('ITEM_ID_Schwab'), 'id': 2}
    tokens['Great_Lakes'] = {'access_token': os.getenv('ACCESS_TOKEN_Lakes'), 'item_id': os.getenv('ITEM_ID_Lakes'), 'id': 3}
    tokens['Capital_One'] = {'access_token': os.getenv('ACCESS_TOKEN_Cap1'), 'item_id': os.getenv('ITEM_ID_Cap1'), 'id': 4}
    return tokens

def getBalance(data):
    return data['accounts'][0]['balances']['current']

def TEST_getTransactions(token, end_date):
    client = TESTplaidClient()
    if token == 'access-development-0b08c2e2-490a-4904-9b06-3f9bad1ac1c8':
        response = client.Transactions.get('access-sandbox-f65f2f09-45f7-43a4-bab8-0c28334334af', '2016-01-01', end_date)

        transactions = response['transactions']
        while len(transactions) < response['total_transactions']:
            pg = len(transactions)/response['total_transactions'] * 100
            print('Chase Progress: ', str(pg) + '%')
            response = client.Transactions.get('access-sandbox-f65f2f09-45f7-43a4-bab8-0c28334334af', '2016-01-01', end_date, offset=len(transactions))

            transactions.extend(response['transactions'])
        balance = response['accounts'][0]['balances']['current']

    else:

        response = client.Transactions.get('access-sandbox-441dcd38-0939-4872-8a84-bd783ca4bbbd', '2016-01-01', end_date)

        transactions = response['transactions']
        while len(transactions) < response['total_transactions']:
            pg = len(transactions)/response['total_transactions'] * 100
            print('Schwab Progress: ', str(pg) + '%')
            response = client.Transactions.get('access-sandbox-441dcd38-0939-4872-8a84-bd783ca4bbbd', '2016-01-01', end_date, offset=len(transactions))

            transactions.extend(response['transactions'])
        balance = response['accounts'][0]['balances']['current']

    return transactions, balance
# Manipulate the count and offset parameters to paginate
# transactions and retrieve all available data



def getTransactions(token, end_date):
    client = plaidClient()
    try:
        response = client.Transactions.get(token,
                                    start_date=date.today().replace(year = date.today().year - 2).strftime('%Y-%m-%d'),
                                    end_date=today_str)
        transactions = response['transactions']

    # Manipulate the count and offset parameters to paginate
    # transactions and retrieve all available data
        while len(transactions) < response['total_transactions']:
            pg = len(transactions)/response['total_transactions'] * 100
            print('Progress: ', str(pg) + '%')
            response = client.Transactions.get(token,
                                            start_date=date.today().replace(year = date.today().year - 2).strftime('%Y-%m-%d')
                                            end_date=today_str,
                                            offset=len(transactions)
                                            )
            transactions.extend(response['transactions'])
            balance = getBalance(response)
        return transactions, balance

    except plaid.errors.PlaidError as e:
        transactions = jsonify({'error': {'display_message': e.display_message, 'error_code': e.code, 'error_type': e.type } })
        balance = jsonify({'error': {'display_message': e.display_message, 'error_code': e.code, 'error_type': e.type } })
        return transactions, balance

def monthStart():
    todayDate = date.today()
    if todayDate.day < 15 and todayDate.month == 1:
        start_year = todayDate.year -1
        month_start = str(start_year) + '-' + str(12) + '-' + str(15)
    elif todayDate.day < 15 and todayDate.month != 1:
        month_start = str(todayDate.year) + '-' + str(todayDate.month - 1) + '-' + str(15)
    else:
        month_start = str(todayDate.year) + '-' + str(todayDate.month) + '-' + str(15)
    return(month_start)

def json2pandaClean(data, exclusions):
    dic_flattened = (flatten(d) for d in data)
    df = pd.DataFrame(dic_flattened)
    df["date"] = pd.to_datetime(df['date'])
    df = df[~df['category_id'].isin(exclusions)]
    df = df.set_index('date')
    df = df.sort_index()
    df = df.loc[df.pending == False]
    return df

def pandaSum(frame):
    return frame['amount'].sum()

def monthlySpending(json, exclusions):
    lcl_frame = json2pandaClean(json, exclusions)
    monthly_sum = lcl_frame.resample('MS', loffset=pd.Timedelta(14, 'd')).sum()
    monthly_sum = monthly_sum['amount']
    return monthly_sum.to_frame()

def progress(json, date, exclusions):
    lcl_df = json2pandaClean(json, exclusions)
    monthly_spending_df = monthlySpending(json, exclusions)
    three_mnth_trailing = monthly_spending_df[-3:]
    threeMave = three_mnth_trailing.mean()
    this_month_df = lcl_df.loc[date:]
    dec = this_month_df['amount'].sum()/threeMave * 100
    dec_rez = dec['amount']
    pct = f'{dec_rez:.2f}' + '%'
    return pct

def curMonthCategories(data, date, exclusions):
    df1 = json2pandaClean(data, exclusions)
    cat_df = df1[:date]
    cat_df = cat_df.groupby('category_1')["amount"].sum()
    df_fram = cat_df.to_frame()

    return df_fram.sort_values(by='category_1', ascending=True)

def categoryHistory(data, exclusions):
    df1 = json2pandaClean(data, exclusions)
    cat_df = df1.groupby('category_1')["amount"].sum()
    df_fram = cat_df.to_frame()
    return df_fram.sort_values(by='category_1', ascending=True)

def cumulativeSum(data, date, exclusions):
    df = json2pandaClean(data, exclusions)
    month_trnsx = df.loc[df.index >= date]
    month_trnsx1 = month_trnsx.resample('D')['amount'].sum().reset_index()
    month_trnsx1['CUMSUM'] = month_trnsx1['amount'].cumsum()
    month_trnsx1 = month_trnsx1.set_index('date')
    return month_trnsx1

def pendingTable(data):
    dic_flattened = (flatten(d) for d in data)
    df = pd.DataFrame(dic_flattened)
    df["date"] = pd.to_datetime(df['date'])
    df = df.set_index('date')
    df = df.sort_index()
    df = df.loc[df.pending == True]
    df1 = df[['account_id','amount', 'category_0', 'category_1', 'category_2', 'name', 'location_city', 'location_state','transaction_type']]
    return df1

def monthsTransactionTable(data, date):
    dic_flattened = (flatten(d) for d in data)
    df = pd.DataFrame(dic_flattened)
    df["date"] = pd.to_datetime(df['date'])
    df = df.set_index('date')
    df = df.sort_index()
    df = df.loc[df.pending == False]
    df = df.loc[df.index >= date]
    df1 = df[['name', 'amount', 'category_0', 'category_1', 'category_2', 'location_city', 'location_state', 'account_id', 'transaction_type']]
    return df1


def cumSpendChart_Update(frame):
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=frame.index,
            y= frame.CUMSUM,
            name="Cumulative Spend"
        ))
    fig.add_trace(
        go.Bar(
            x=frame.index,
            y=frame.amount,
            name="Daily Spend"
        ))
    fig.update_layout(title_text="Cumulative Spending")

    py.plot(fig, filename="CumulativeSpendingChart.html", auto_open=False)
    return 'Updated'

def plotlyCategoryChart_Update(frame):
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y = frame.index,
            x = frame.amount,
            orientation='h'
        ))
    fig.update_layout(title_text="This Month's Spending by Category")
    py.plot(fig, filename="CurrentMonthCategory.html", auto_open=False)
    return 'Success'

def plotlyCategoryHistory_Update(frame):
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y = frame.index,
            x = frame.amount,
            orientation='h'
        ))
    fig.update_layout(title_text="Historical Spending by Category")
    py.plot(fig, filename="ALLMonthCategory.html", auto_open=False)
    return 'Success'

def plotlyMonthlyChart(frame):
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x = frame.index,
            y = frame.amount
        ))
    fig.update_layout(title_text="Monthly Total Spending")
    py.plot(fig, filename="HistoricalSpending.html", auto_open=False)
    return 'Success'

def plotlyTtable(frame):
    values = list(frame.columns)
    values.insert(0, 'date')
    fig = go.Figure()
    fig.add_trace(
        go.Table(
            header=dict(values=values,
                    fill_color='paleturquoise',
                    align='left'),
        cells=dict(values=[frame.index, frame.name, frame.amount, frame.category_0, frame.category_1, frame.category_2, frame.location_city, frame.location_state, frame.account_id, frame.transaction_type],
                   fill_color='lavender',
                   align='left')
        ))

    fig.update_layout(title_text="This Month's Transactions")
    py.plot(fig, filename="MonthlyTable.html", auto_open=False)
    return 'Success'

def plotlyPtable(frame):
    values = list(frame.columns)
    values.insert(0, 'date')
    fig = go.Figure()
    fig.add_trace(
        go.Table(
            header=dict(values=values,
                    fill_color='paleturquoise',
                    align='left'),
        cells=dict(values=[frame.index, frame.name, frame.amount, frame.category_0, frame.category_1, frame.category_2, frame.location_city, frame.location_state, frame.account_id, frame.transaction_type],
                   fill_color='lavender',
                   align='left')
        ))

    fig.update_layout(title_text="Pending Transactions")
    py.plot(fig, filename="PendingTable.html", auto_open=False)
    return 'Success'

def htmlGraph(graphs):
  template = (''
    '<a href="{graph_url}" target="_blank">' # Open the interactive graph when you click on the image
        '<img src="{graph_url}.png">'        # Use the ".png" magic url so that the latest, most-up-to-date image is included
    '</a>'
    '{caption}'                              # Optional caption to include below the graph
    '<br>'                                   # Line break
    '<a href="{graph_url}" style="color: rgb(190,190,190); text-decoration: none; font-weight: 200;" target="_blank">'
        'Click to comment and see the interactive graph'  # Direct readers to Plotly for commenting, interactive graph
    '</a>'
    '<br>'
    '<hr>'                                   # horizontal line
    '')

  email_body = ''
  for graph in graphs:
    _ = template
    _ = _.format(graph_url=graph, caption='')
    email_body += _
  return email_body

def htmlTable(tables, html_body):
    template = (''
    '<a href="{graph_url}" target="_blank">' # Open the interactive graph when you click on the image
        '<img src="{graph_url}.png">'        # Use the ".png" magic url so that the latest, most-up-to-date image is included
    '</a>'
    '{caption}'                              # Optional caption to include below the graph
    '<br>'                                   # Line break
    '<a href="{graph_url}" style="color: rgb(190,190,190); text-decoration: none; font-weight: 200;" target="_blank">'
        'Click to comment and see the interactive graph'  # Direct readers to Plotly for commenting, interactive graph
    '</a>'
    '<br>'
    '<hr>'                                   # horizontal line
    '')

    for table in tables:
        _ = template
        _ = _.format(graph_url=table, caption='')
        html_body += _
    return html_body


def generate_HTML(balance_chase, balance_schwab, charts_tables, chase_total, schwab_total, balance_great_lakes, balance_cap_one):
    # Create the jinja2 environment.
    # Notice the use of trim_blocks, which greatly helps control whitespace.
    j2_env = Environment(loader=FileSystemLoader('./templates'),
                         trim_blocks=True)
    template_ready = j2_env.get_template('hawkplate.html').render(
        Date=today_str,
        Chase_Balance=balance_chase,
        Schwab_Balance=balance_schwab,
        charts_and_tables=charts_tables,
        Chase_Spent=chase_total,
        Schwab_Spent=schwab_total,
        Capital_One_Balance=balance_cap_one,
        Great_Lakes_Balance=balance_great_lakes
    )
    return template_ready

def jinjaTEST(balone, baltwo):
    j2_env = Environment(loader=FileSystemLoader('./templates'),
                         trim_blocks=True)
    template_ready = j2_env.get_template('hawkplate.html').render(
        Date=today_str,
        Chase_Balance=balone,
        Schwab_Balance=baltwo

    )
    return template_ready

def emailPreview(mail):
    prev = open('templates/email_preview.html','w')
    prev.write(mail)
    prev.close()
