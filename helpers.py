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
import math


today_str = str(date.today())

chart_studio.tools.set_credentials_file(username=os.getenv('PLOTLY_USERNAME'), api_key=os.getenv('PLOTLY_API_KEY'))

def plaidClient():
    client = plaid.Client(os.getenv('PLAID_CLIENT_ID'),
                          os.getenv('PLAID_SECRET'),
                          os.getenv('PLAID_PUBLIC_KEY'),
                          os.getenv('PLAID_ENV'),
                          api_version='2018-05-22')
    return client

def SANDBOXplaidClient():
    client = plaid.Client(os.getenv('PLAID_CLIENT_ID'),
                        os.getenv('PLAID_SECRET'),
                        os.getenv('PLAID_PUBLIC_KEY'),
                        os.getenv('TEST_PLAID_ENV'),
                        api_version='2018-05-22')
    return client

def plaidTokens():
    tokens = {}
    tokens['Chase'] = {'access_token': os.getenv('ACCESS_TOKEN_Chase'), 'item_id': os.getenv('ITEM_ID_Chase'), 'sandbox':os.getenv('ACCESS_TOKEN_Chase_SANDBOX')}
    tokens['Schwab'] = {'access_token': os.getenv('ACCESS_TOKEN_Schwab'), 'item_id': os.getenv('ITEM_ID_Schwab'), 'sandbox':os.getenv('ACCESS_TOKEN_Schwab_SANDBOX')}
    tokens['Great_Lakes'] = {'access_token': os.getenv('ACCESS_TOKEN_Lakes'), 'item_id': os.getenv('ITEM_ID_Lakes'), 'sandbox': os.getenv('ACCESS_TOKEN_Lakes_SANDBOX')}
    tokens['Capital_One'] = {'access_token': os.getenv('ACCESS_TOKEN_Cap1'), 'item_id': os.getenv('ITEM_ID_Cap1'), 'sandbox': os.getenv('ACCESS_TOKEN_Cap1_SANDBOX')}
    return tokens

def getBalance(data):
    return '$' + str(data['accounts'][0]['balances']['current'])

def idToken(token):
    tokens = plaidTokens()
    for k, v in tokens.items():
        if v['access_token'] == token:
            item = k
        elif v['sandbox'] == token:
            item = k
    return item

def logResponse(response):
    with open('templates/plaid_response.json','w') as file:
        json.dump(response, file, sort_keys=True, indent=4)
        file.close()
    return 'Response Logged to plaid_response.json'

def getTransactions(client, token, start_date, end_date):
    try:
        account_ids = [account['account_id'] for account in client.Accounts.get(token)['accounts']]
        print(" {} Account ID's".format(idToken(token)))
        print(account_ids)

        response = client.Transactions.get(token, start_date, end_date, account_ids=account_ids)
        rez = logResponse(response)
        print(rez)
        balance = getBalance(response)
        num_available_transactions= response['total_transactions']
        print("{} Transactions Recieved from Plaid".format(num_available_transactions))
        num_pages = math.ceil(num_available_transactions / 500)
        transactions = []

        for page_num in range(num_pages):
            print("{}% Complete".format(page_num/num_pages * 100))
            transactions += [transaction for transaction in client.Transactions.get(token, start_date, end_date, account_ids=account_ids, offset=page_num * 500, count=500)['transactions']]


        return transactions, balance

    except plaid.errors.PlaidError as e:
        print(json.dumps({'error': {'display_message': e.display_message, 'error_code': e.code, 'error_type': e.type } }))
        transactions = {'result': e.code}
        balance = {'result': e.code}
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

def clear_data_file():
    open('templates/data.txt', "w").close()
    return 'Data Text File Cleared'

def cap1_lakes_get(client, token, start_date, end_date):
    account_ids = [account['account_id'] for account in client.Accounts.get(token)['accounts']]
    print(" {} Account ID's".format(idToken(token)))
    print(account_ids)
    response = client.Transactions.get(token, start_date, end_date, account_ids=account_ids)
    return response

def lakesData(data):
    act_list = data['accounts']
    balance_sum = 0
    for a in act_list:
        balance_sum += int(a['balances']['current'])

    pmt_list = data['transactions']
    pmt_totals = 0
    for p in pmt_list:
        pmt_totals += int(p['amount'])

    return balance_sum, pmt_totals


def json2pandaClean(data, exclusions):
    for e in exclusions:
        print('exclude: ', e)
    flat_list = []
    with open('templates/data.txt','a') as file:
        file.write(json.dumps(data))
        file.close()
    for d in data:
        try:
            dic_flattened = flatten(d)
            flat_list.append(dic_flattened)
        except:
            print('cant flatten: ', type(d))
            print(d)
            pass

    df = pd.DataFrame(flat_list)
    df["date"] = pd.to_datetime(df['date'])
    df = df[~df['category_id'].isin(exclusions)]
    df = df.set_index('date')
    df = df.sort_index()
    df = df.loc[df.pending == False]
    return df

def pandaSum(frame):
    fsum = frame['amount'].sum()
    sum_str = f'{fsum:.2f}'
    return '$' + sum_str

def monthlySpending(json, exclusions, date):
    lcl_frame = json2pandaClean(json, exclusions)
    monthly_sum = lcl_frame.resample('D', loffset=pd.Timedelta(14, 'd')).sum()
    monthly_sum = monthly_sum.loc[monthly_sum.index >= date]
    monthly_sum = monthly_sum['amount']
    return monthly_sum.to_frame()

def progress(json, date, exclusions):
    lcl_df = json2pandaClean(json, exclusions)
    monthly_spending_df = monthlySpending(json, exclusions, date)
    three_mnth_trailing = monthly_spending_df[-3:]
    threeMave = three_mnth_trailing.mean()
    this_month_df = lcl_df.loc[date:]
    dec = this_month_df['amount'].sum()/threeMave * 100
    dec_rez = dec['amount']
    pct = f'{dec_rez:.2f}' + '%'
    return pct

def curMonthCategories(data, date, exclusions):
    df1 = json2pandaClean(data, exclusions)
    cat_df = df1.loc[df1.index >= date]
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
    print('Updating Plotly Cumulative Chart')
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
    return 'Cumulative Chart Updated'

def plotlyCategoryChart_Update(frame):
    print('Updating Plotly Category Chart')
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y = frame.index,
            x = frame.amount,
            orientation='h'
        ))
    fig.update_layout(title_text="This Month's Spending by Category")
    py.plot(fig, filename="CurrentMonthCategory.html", auto_open=False)
    return 'Plotly Category Chart Updated'

def plotlyCategoryHistory_Update(frame):
    print('Updating Plotly Category History Chart')
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y = frame.index,
            x = frame.amount,
            orientation='h'
        ))
    fig.update_layout(title_text="Historical Spending by Category")
    py.plot(fig, filename="ALLMonthCategory.html", auto_open=False)
    return 'Plotly Category History Chart Updated'

def plotlyMonthlyChart(frame):
    print('Updating Plotly Monthly Chart')
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x = frame.index,
            y = frame.amount
        ))
    fig.update_layout(title_text="Monthly Total Spending")
    py.plot(fig, filename="HistoricalSpending.html", auto_open=False)
    return 'Plotly Monthly Chart Updated'

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


def generate_HTML(balance_chase, balance_schwab, charts_tables, chase_total, schwab_total, cap1_total, balance_great_lakes, balance_cap_one):
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
        Capital1_Spend=cap1_total,
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
