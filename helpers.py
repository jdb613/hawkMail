from flatten_json import flatten
import pandas as pd
from datetime import datetime, timedelta, date
import chart_studio.plotly as py
import plotly.graph_objects as go
import plotly as plotly
import chart_studio
from plotly.subplots import make_subplots
import plotly.figure_factory as ff
import plotly.io as pio
import plaid
from plaid.errors import APIError, ItemError
import requests
import json
from plaid import Client
from jinja2 import Environment, FileSystemLoader
import os
import math
import locale
from scipy import stats
import numpy as np
import re

locale.setlocale( locale.LC_ALL, '' )
pio.templates.default = "seaborn"
today_str = str(date.today())
hawk_mode = str(os.getenv('HAWK_MODE'))

############### Utilities ###############
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
    return currencyConvert(data['accounts'][0]['balances']['current'])

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
        print(f"**** New Response **** ", file=file)
        json.dump(response, file, sort_keys=True, indent=4)
        file.close()
    return 'Response Logged to plaid_response.json'

def clear_data_file():
    open('templates/data.txt', "w").close()
    open('templates/email_preview', "w").close()
    return 'Data Text File Cleared'

def monthStart():
    todayDate = date.today()
    if todayDate.day < 15 and todayDate.month == 1:
        start_year = todayDate.year -1
        month_start = str(start_year) + '-' + str(12) + '-' + str(15)
    elif todayDate.day < 15 and todayDate.month != 1:
        month_start = str(todayDate.year) + '-' + str(todayDate.month - 1) + '-' + str(15)
    else:
        month_start = str(todayDate.year) + '-' + str(todayDate.month) + '-' + str(15)
    print('Start Date of Current Billing Period: ', datetime.strptime(month_start, '%Y-%m-%d').strftime('%m/%d/%y'))

    return month_start


def json2pandaClean(data, exclusions):
    flat_list = []
    with open('templates/data.txt','a') as file:
        try:
            file.write(json.dumps(data))
        except:
            file.write(json.dumps(str(data)))
        file.close()
    for d in data:

        try:
            dic_flattened = flatten(d)
            flat_list.append(dic_flattened)
            df = pd.DataFrame(flat_list)
            df["date"] = pd.to_datetime(df['date'])
            df = df[~df['category_id'].isin(exclusions)]
            df = df.set_index('date')
            df = df.sort_index()
            # df = df.loc[df.pending == False]
        except:
            print('cant flatten: ', type(d))
            print(d)
            df = pd.DataFrame()
    return df


def pandaSum(frame):
    frame = frame.loc[frame.index >= monthStart()]
    fsum = frame['amount'].sum()
    return currencyConvert(fsum)


def drop_columns(df):
    df = df.drop(columns=['location_address', 'location_city', 'location_lat',
       'location_lon', 'location_state', 'location_store_number','account_owner','payment_meta_by_order_of',
       'payment_meta_payee', 'payment_meta_payer',
       'payment_meta_payment_method', 'payment_meta_payment_processor',
       'payment_meta_ppd_id', 'payment_meta_reason',
       'payment_meta_reference_number','pending_transaction_id', 'transaction_id', 'pending'])
    return df


def tidy_df(df, hawk_mode):
    if hawk_mode == 'sandbox':
        client = SANDBOXplaidClient()
        tokens = plaidTokens()
        chase_ids = [account['account_id'] for account in client.Accounts.get(tokens['Chase']['sandbox'])['accounts']]
        schwab_ids = [account['account_id'] for account in client.Accounts.get(tokens['Schwab']['sandbox'])['accounts']]
        all_ids = chase_ids + schwab_ids
        df = df[df['account_id'].isin(all_ids)]
    else:
        df['account_id'] = df['account_id'].map({'LOgERxzqrNFLPZdyNx7oFb9JwX39wzU05vVvd': 'Chase', 'vqmBXOzaoOuxNRe533YbhrV4r0NqELCmZr5vX': 'Schwab'})
    df=df.rename(columns = {'account_id':'account'})
    tdfst = df[['account', 'amount', 'name', 'category_0', 'category_1', 'category_2']]
    #df.index = df.index.strftime('%m/%d/%y')
    return tdfst


def paymentFinder(json):
    df = pd.DataFrame(json)
    df["date"] = pd.to_datetime(df['date'])
    df = df.set_index('date')
    df = df.loc[df['category_id'] == '16001000']
    df = df.loc[df['pending'] == False]
    monthly_sum = df.resample('M', loffset=pd.Timedelta(-16, 'd')).sum()
    return monthly_sum


def currencyConvert(x):
    return '${:,.2f}'.format(x)


def tableTidy(df, hawk_mode):
    df = drop_columns(df)
    df = tidy_df(df, hawk_mode)
    df = df.sort_index()
    df = df.reset_index()
    if df.empty == False:
        print('False')
        df['date'] = df['date'].dt.strftime('%m/%d/%y')
        df['name'] = df['name'].str.capitalize()
        df['amount'] = df['amount'].apply(currencyConvert)
    df.columns = map(str.capitalize, df.columns)
    return df


def chartLINK(filename):
    try:
        url = py.plot(fig, filename=c)
        return url.resource
    except:
        return 'Link Not Found'

def lakesData(data):
    act_list = data['accounts']
    balance_sum = 0
    for a in act_list:
        balance_sum += int(a['balances']['current'])

    pmt_list = data['transactions']
    pmt_totals = 0
    for p in pmt_list:
        pmt_totals += int(p['amount'])

    return currencyConvert(balance_sum), currencyConvert(pmt_totals)


############### API Interactions ###############
def getTransactions(client, token, start_date, end_date):
    try:
        account_ids = [account['account_id'] for account in client.Accounts.get(token)['accounts']]
        print(" {} Account ID's".format(idToken(token)))
        print(len(account_ids))

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
        print('full error: ', e)
        transactions = {'result': e.code}
        balance = {'result': e.code}

        return transactions, balance


def cap1_lakes_get(client, token, start_date, end_date):
    account_ids = [account['account_id'] for account in client.Accounts.get(token)['accounts']]
    print(" {} Account ID's".format(idToken(token)))
    print(len(account_ids))
    response = client.Transactions.get(token, start_date, end_date, account_ids=account_ids)
    return response


def getData(environment, exclusions):
    master_data = {}
    tokens = plaidTokens()
    today_str = str(date.today())

    if environment == 'sandbox':
        client = SANDBOXplaidClient()
        start_date = date.today().replace(year = date.today().year - 2).strftime('%Y-%m-%d')
        trnsx_chase, master_data['balance_chase'] = getTransactions(client, tokens['Chase']['sandbox'], start_date, today_str)
        trnsx_schwab, master_data['balance_schwab'] = getTransactions(client, tokens['Schwab']['sandbox'], start_date, today_str)
        cap1_response = cap1_lakes_get(client, tokens['Capital_One']['sandbox'], start_date, today_str)
        lakes_response = cap1_lakes_get(client, tokens['Great_Lakes']['sandbox'], start_date, today_str)

    elif environment == 'testing' or environment == 'local_testing':
        client = plaidClient()
        start_date = date.today() - timedelta(days=90)
        trnsx_chase, master_data['balance_chase'] = getTransactions(client, tokens['Chase']['access_token'], start_date.strftime('%Y-%m-%d'), today_str)
        trnsx_schwab, master_data['balance_schwab'] = getTransactions(client, tokens['Schwab']['access_token'], start_date.strftime('%Y-%m-%d'), today_str)
        cap1_response = cap1_lakes_get(client, tokens['Capital_One']['access_token'], start_date.strftime('%Y-%m-%d'), today_str)
        lakes_response = cap1_lakes_get(client, tokens['Great_Lakes']['access_token'], start_date.strftime('%Y-%m-%d'), today_str)


    elif environment == 'production':
        client = plaidClient()
        start_date = date.today().replace(year = date.today().year - 2).strftime('%Y-%m-%d')
        trnsx_chase, master_data['balance_chase'] = getTransactions(client, tokens['Chase']['access_token'], start_date, today_str)
        trnsx_schwab, master_data['balance_schwab'] = getTransactions(client, tokens['Schwab']['access_token'], start_date, today_str)
        cap1_response = cap1_lakes_get(client, tokens['Capital_One']['access_token'], start_date, today_str)
        lakes_response = cap1_lakes_get(client, tokens['Great_Lakes']['access_token'], start_date, today_str)

    try:
        master_data['chase_total'] = pandaSum(json2pandaClean(trnsx_chase, exclusions))
        master_data['schwab_total'] = pandaSum(json2pandaClean(trnsx_schwab, exclusions))
        master_data['lakes_balance'], master_data['lakes_total'] = lakesData(lakes_response)
        master_data['cap1_balance'], master_data['cap1_total'] = lakesData(cap1_response)
        master_data['all_trnsx'] = trnsx_chase + trnsx_schwab


    except Exception as e:

        master_data['chase_total'] = 0
        master_data['schwab_total'] = 0
        master_data['cap1_total'] = 0
        master_data['lakes_total'] = 0
        master_data['cap1_balance'] = 0
        master_data['lakes_balance'] = 0
        master_data['all_trnsx'] = {'error': e}
        print('Exception!!', master_data['all_trnsx'])
    return master_data

############## Data Vizualization ##############
def progress(json, date, exclusions, hawk_mode):
    lcl_df = json2pandaClean(json, exclusions)
    lcl_df = lcl_df.loc[lcl_df.pending == False]
    monthly_spending_df, URL = monthlySpending(json, exclusions, hawk_mode, 'No')
    print('*** Monthly Spending Progress ***')
    print(monthly_spending_df)
    three_mnth_trailing = monthly_spending_df[-3:]
    print('3 Month Trailing')
    print(three_mnth_trailing)
    threeMave = three_mnth_trailing.mean()
    print('T3M Spending: ', threeMave)
    this_month_df = lcl_df.loc[date:]
    print('Total Spending this Month: ', this_month_df['amount'].sum())
    dec = this_month_df['amount'].sum()/threeMave * 100
    dec_rez = int(round(dec['amount']))
    # rpct = f'{(100 - dec_rez):.2f}' + '%'
    # pct = f'{dec_rez:.2f}' + '%'

    pct = dec_rez
    rpct = 100 - dec_rez
    progHTML = '<td bgcolor="#f83f83" style="width:'
    progHTML += str(pct)
    progHTML += '%; background-color:#f83f83; float:left; height:15px;text-align: center;">'
    progHTML += str(pct)
    progHTML += '%</td><td bgcolor="#cccccc" style="width:'
    progHTML += str(rpct)
    progHTML += '%; background-color:#cccccc; float:left; height:15px;"></td>'
    return progHTML

def cumulativeSum(data, date, exclusions, hawk_mode):
    df = json2pandaClean(data, exclusions)
    df = df.loc[df.pending == False]
    month_trnsx = df.loc[df.index >= date]
    month_trnsx1 = month_trnsx.resample('D')['amount'].sum().reset_index()
    month_trnsx1['CUMSUM'] = month_trnsx1['amount'].cumsum()
    month_trnsx1 = month_trnsx1.set_index('date')
    print('*** Cumulative Sum Result ***')
    print(month_trnsx1.head())
    print('Updating Plotly Cumulative Chart')
    fig = go.Figure(
        data=[
            go.Scatter(name='Cumulative Spending', x=month_trnsx1.index.tolist(), y=month_trnsx1.CUMSUM.tolist(), yaxis="y2"),
            go.Bar(name='Daily Spend', x=month_trnsx1.index.tolist(), y=month_trnsx1.amount.tolist(),
                text = [str('<b>' + locale.currency(i) + '</b>') for i in month_trnsx1.amount.tolist()],
                textposition='auto')
        ],
        layout=go.Layout(
            title=go.layout.Title(text="Cumulative Spending")
        ))
    fig.update_xaxes(nticks=len(month_trnsx1), tickangle=45)
    fig.update_layout(
            yaxis=dict(
                title="Daily Spend"
            ),
            yaxis2=dict(
                title="Cumulative",
                anchor="x",
                overlaying="y",
                side="right"
            ))
    try:
        if hawk_mode == 'sandbox' or hawk_mode == 'local_testing':
            URL = plotly.offline.plot(fig, include_plotlyjs=True, output_type='div')
        else:
            URL = py.plot(fig, filename="CumulativeSpending", auto_open=False)
        return URL
    except Exception as e:
        return '{}% Chart Update Error'.format("CumulativeSpending")


def monthlySpending(json, exclusions, hawk_mode, flag):
    tokens = plaidTokens()
    chase_names = ['Chase']
    schwab_names = ['Schwab']
    all_names = chase_names + schwab_names
    sum_frame = json2pandaClean(json, exclusions)
    sum_frame = sum_frame.loc[sum_frame.pending == False]
    sum_frame = drop_columns(sum_frame)
    sum_frame = tidy_df(sum_frame, hawk_mode)

    if hawk_mode == 'sandbox':
        client = SANDBOXplaidClient()
        chase_acts = [account['account_id'] for account in client.Accounts.get(tokens['Chase']['sandbox'])['accounts']]
        schwab_acts = [account['account_id'] for account in client.Accounts.get(tokens['Schwab']['sandbox'])['accounts']]
        all_acts = chase_acts + schwab_acts
        chase_frame = sum_frame[sum_frame['account'].isin(chase_acts)]
        schwab_frame = sum_frame[sum_frame['account'].isin(schwab_acts)]
        both_frames = sum_frame[sum_frame['account'].isin(all_acts)]
    else:
        client = plaidClient()

        chase_frame = sum_frame[sum_frame['account'].isin(chase_names)]
        schwab_frame = sum_frame[sum_frame['account'].isin(schwab_names)]
        both_frames = sum_frame[sum_frame['account'].isin(all_names)]

    Smonthly_sum = schwab_frame.resample('M', loffset=pd.Timedelta(-16, 'd')).sum()
    Cmonthly_sum = chase_frame.resample('M', loffset=pd.Timedelta(-16, 'd')).sum()
    both_frames = both_frames.resample('M', loffset=pd.Timedelta(-16, 'd')).sum()
    print('*** Monthly Spending Result ***')
    print(both_frames.head())
    cc_payments = paymentFinder(json)

    if flag == 'Yes':
        print('Updating Plotly Monthly Chart')
        fig = go.Figure(
        data=[
        go.Bar(name='Chase', x=Cmonthly_sum.index.tolist(), y=Cmonthly_sum.amount.tolist(),
                text = [locale.currency(i) for i in Cmonthly_sum.amount.tolist()],
                textposition='auto'),
        go.Bar(name='Schwab', x=Smonthly_sum.index.tolist(), y=Smonthly_sum.amount.tolist(),
                text = [locale.currency(i) for i in Smonthly_sum.amount.tolist()],
                textposition='auto')
        ],
        layout=go.Layout(
            title=go.layout.Title(text="Monthly Spending")
        ))
        fig.update_xaxes(rangemode="normal", showgrid=True, ticks="outside", tickson="boundaries")
        fig.update_layout(barmode='stack')

        for i in range(len(cc_payments.amount.to_list())):
            start = cc_payments.index[i]
            fig.add_shape(
                # Line Horizontal
                go.layout.Shape(
                    type="line",
                    x0= start ,
                    y0=cc_payments.iloc[i].amount,
                    x1=start,
                    y1=cc_payments.iloc[i].amount
            ))
        fig.update_shapes(dict(xref='x', yref='y'))

        if hawk_mode == 'sandbox' or hawk_mode == 'local_testing':
            URL = plotly.offline.plot(fig, include_plotlyjs=True, output_type='div')
        else:
            URL = py.plot(fig, filename="monthly_spending", auto_open=False)
    else:
        URL = 'Update Not Requested'
    return both_frames, URL


def curMonthCategories(data, date, exclusions, hawk_mode):
    df1 = json2pandaClean(data, exclusions)
    df1 = df1.loc[df1.pending == False]
    print('*** Current Month Category Before: ', len(df1))
    cat_df = df1.loc[df1.index >= date]
    print('*** Current Month Category After: ', len(cat_df))
    cat_df = cat_df.groupby('category_1')["amount"].sum()
    df_fram = cat_df.to_frame()
    df_fram = df_fram[-15:].sort_values(by='amount', ascending=False)
    df_fram['amount'] = df_fram['amount'].apply(locale.currency)
    print("*** This Month's Categories ***")
    print(df_fram.head())
    print('Updating Plotly Category Chart')
    fig = go.Figure(
        data = [
            go.Bar(
                name="Category Spend",
                y=df_fram.index.tolist(),
                x=df_fram.amount.values.tolist(),
                text=df_fram.amount.values.tolist(),
                textposition='auto',
                orientation='h')
            ],
        layout=go.Layout(
            title=go.layout.Title(text="This Month's Spending by Category")
        ))

    if hawk_mode == 'sandbox' or hawk_mode == 'local_testing':
        URL = plotly.offline.plot(fig, include_plotlyjs=True, output_type='div')
    else:
        URL = py.plot(fig, filename="CurrentMonthCategory", auto_open=False)
    return URL

def categorySubplots(data, date, exclusions, hawk_mode):
    df = json2pandaClean(data, exclusions)
    df = df.loc[df.pending == False]
    df1 = drop_columns(df)
    df2 = tidy_df(df1, hawk_mode)
    df3 = df2.loc[monthStart():]
    category_df = df3.groupby('category_0')['amount'].sum().nlargest(5)
    print('**** Top Categories This Month ***')
    print(category_df.head())
    titles = ['Top Categories This Month']
    for i in range(len(category_df)):
        titles.append(category_df.index[i])
        titles.append(category_df.index[i] + str(' Table'))


    fig = make_subplots(rows=11, cols=1, subplot_titles=titles, vertical_spacing=0.02,
                    specs=[[{"type": "bar"}],
                            [{"type": "bar"}],
                            [{"type": "table"}],
                            [{"type": "bar"}],
                            [{"type": "table"}],
                            [{"type": "bar"}],
                            [{"type": "table"}],
                            [{"type": "bar"}],
                            [{"type": "table"}],
                            [{"type": "bar"}],
                            [{"type": "table"}]])

    category_summary_trace = go.Bar(
            x=[locale.currency(j) for j in category_df.values.tolist()],
            y=category_df.index.tolist(),
            text=category_df.index.tolist(),
            textposition='auto',
            orientation='h')

    fig.append_trace(category_summary_trace, 1, 1)

    row = 2

    for i in range(len(category_df)):
        cat_data = df3[df3['category_0'] == category_df.index[i]]
        table_data = cat_data.reset_index()
        table_data['date'] = table_data['date'].dt.strftime('%m/%d/%y')
        table_data['name'] = table_data['name'].str.capitalize()
        table_data['amount'] = table_data['amount'].apply(currencyConvert)
        table_data.columns = map(str.capitalize, table_data.columns)

        plt_data = cat_data.groupby('name')['amount'].sum().sort_values()[-15:]

        print('Updating Top Category: {}'.format(category_df.index[i]))

        bar_trace = go.Bar(
                text = ['<b>' + i + '</b>' for i in plt_data.index.tolist()],
                textposition='auto',
                x=[locale.currency(j) for j in plt_data.values.tolist()],
                y=plt_data.index.tolist(),
                orientation='h')

        table_trace = go.Table(
            header=dict(
                values=table_data.columns.tolist(),
                font=dict(size=15),
                align="left"
            ),
            cells=dict(
                values=[table_data[k].tolist() for k in table_data.columns],
                align = "left")
        )

        fig.append_trace(bar_trace, row, 1)
        fig.append_trace(table_trace, row+1, 1)

        row += 2
    fig['layout'].update(height=3000, width=1000)
    fig.update_yaxes(showticklabels=False)
    if hawk_mode == 'sandbox'  or hawk_mode == 'local_testing':
        URL = plotly.offline.plot(fig, include_plotlyjs=True, output_type='div')
    else:
        filename='CategorySubplots'
        URL = py.plot(fig, filename=filename, auto_open=False)
    return URL


def categoryHistory(data, exclusions, hawk_mode):
    df1 = json2pandaClean(data, exclusions)
    df1 = df1.loc[df1.pending == False]
    cat_df = df1.groupby('category_1')["amount"].sum()
    df_fram = cat_df.to_frame()
    df_fram = df_fram[-15:].sort_values(by='amount', ascending=True)
    print('*** Category History ***')
    print(df_fram.head())
    print('Updating Plotly Category Chart')
    fig = go.Figure(
        data = [
            go.Bar(
                name="Category Spend Historically",
                y=df_fram.index.tolist(),
                x=df_fram.amount.values.tolist(),
                orientation='h')
            ],
        layout=go.Layout(
            title=go.layout.Title(text="Historical Spending by Category")
        ))
    annotations = []
    for yd, xd in zip(df_fram.index.tolist(), df_fram.amount.values.tolist()):
        annotations.append(dict(xref='x1', yref='y1',
                                y=yd, x=xd + 100,
                                text=locale.currency(xd),
                                font=dict(family='Arial', size=12)))
    fig.update_layout(annotations=annotations)
    if hawk_mode == 'sandbox' or hawk_mode == 'local_testing':
        URL = plotly.offline.plot(fig, include_plotlyjs=True, output_type='div')
    else:
        URL = py.plot(fig, filename="CategoryHistory", auto_open=False)

    return df_fram.sort_values(by='category_1', ascending=True), URL

def relativeCategories(data, date, exclusions, hawk_mode):
    df1 = json2pandaClean(data, exclusions)
    df1 = df1.loc[df1.pending == False]
    df1 = drop_columns(df1)
    df1 = tidy_df(df1, hawk_mode)

    df_mean = df1.groupby([pd.Grouper(freq='M'), 'category_1'])['amount'].mean().unstack().mean(axis=0)

    df_current = df1.loc['2019-10-15':]
    df_current = df_current.groupby('category_1')['amount'].mean()

    combined = pd.concat([df_current, df_mean], axis=1, sort=True).dropna()
    combined.columns = ['This Month', 'Average']
    combined = combined.sort_values('This Month')
    z = np.abs(stats.zscore(combined))
    comb = combined[(z < 4).all(axis=1)].sort_values('This Month')
    print('*** Relative Categories ***')
    print(comb.head())
    fig = go.Figure()
    fig.add_trace(go.Bar(x=comb.index.tolist(),
                    y=comb['This Month'].tolist(),
                    name='This Month'
                    ))
    fig.add_trace(go.Bar(x=comb.index.tolist(),
                    y=comb['Average'].tolist(),
                    name='Average'
                    ))

    fig.update_layout(
        title='Relative Category Spending',
        xaxis=dict(
            title='Category',
            tickangle=45
        ),
        yaxis=dict(
            title='Spent'
        ),
        legend=dict(
            x=0,
            y=1.0
        ),
        barmode='group'
    )
    fig.update_yaxes(automargin=True)
    if hawk_mode == 'sandbox' or hawk_mode == 'local_testing':
        URL = plotly.offline.plot(fig, include_plotlyjs=True, output_type='div')
    else:
        URL = py.plot(fig, filename="RelativeCategory", auto_open=False)
    return URL


def transactionTables(data, date, exclusions, hawk_mode):
    print('Date: ', datetime.strptime(date, '%Y-%m-%d').strftime('%m/%d/%y'))
    df = json2pandaClean(data, exclusions)
    df_pending = df.loc[df.pending == True]
    df_posted = df.loc[df.pending == False]
    df_pending_tidy = tableTidy(df_pending, hawk_mode)
    df_posted_tidy = tableTidy(df_posted, hawk_mode)
    print('*** Posted Before: ', len(df_posted_tidy))
    df_current_posted = df_posted_tidy.loc[df_posted_tidy['Date'] >= datetime.strptime(date, '%Y-%m-%d').strftime('%m/%d/%y')]
    print('*** Posted After: ', len(df_current_posted))
    df_current_pending = df_pending_tidy.loc[df_pending_tidy['Date'] >= datetime.strptime(date, '%Y-%m-%d').strftime('%m/%d/%y')]
    print('**** Pending ****')
    print(df_current_pending.head())
    print('*** Posted ***')
    print(df_current_posted.head())

    return df_current_posted.to_html(), df_current_pending.to_html()

def jumboTable(data, date, exclusions, hawk_mode):
    df = json2pandaClean(data, exclusions)
    df_posted = df.loc[df.pending == False]
    df_posted_tidy = tableTidy(df_posted, hawk_mode)
    df_posted_tidy = df_posted_tidy.loc[df_posted_tidy['Date'] >= datetime.strptime(date, '%Y-%m-%d').strftime('%m/%d/%y')]
    df_posted_tidy['Amount'] = df_posted_tidy['Amount'].replace( '[\$,)]','', regex=True ).replace( '[(]','-',   regex=True ).astype(float)
    df_posted_tidy = df_posted_tidy.loc[df_posted_tidy.Amount >= 100]
    return df_posted_tidy.to_html()
################ HTML Generation ################
def chartConvert(chart_link_lists):
    return [htmlGraph(c) for c in chart_link_lists]

def htmlGraph(graph):
    print('Graph Data for HTML: ', graph)
    template = (''
        '<td align="center" bgcolor="#E5DFDF">'
        '<a href="{graph_url}" target="_blank">' # Open the interactive graph when you click on the image
            '<img src="{graph_url}.png">'        # Use the ".png" magic url so that the latest, most-up-to-date image is included
        '</a>'
        '{caption}'                              # Optional caption to include below the graph
        '<br>'                                   # Line break
        '<a href="{graph_url}" style="color: rgb(190,190,190); text-decoration: none; font-weight: 200;" target="_blank">'
            'Click to comment and see the interactive graph'  # Direct readers to Plotly for commenting, interactive graph
        '</a>'
        '<br>'
        '<hr>'
        '</td><td bgcolor="#E5DFDF" style="font-size: 0; line-height: 0;" width="10">&nbsp;</td>'                                   # horizontal line
        '')

    email_body = ''
    print('Graph TEST: ', graph)
    _ = template
    _ = _.format(graph_url=graph, caption='')
    email_body += _
    return email_body


def jinjaTEST(data, hawk_mode):
    j2_env = Environment(loader=FileSystemLoader('./templates'),
                         trim_blocks=True)
    template_ready = j2_env.get_template('newhawk.html').render(
            jinja_data=data
        )
    return template_ready

def emailPreview(mail, hawk_mode):
    prev = open('templates/email_preview.html','w')
    prev.write(mail)
    prev.close()
    return 'Preview File Updated'







########## Plotly Charts ########

# def plotlyTopCategoryNameChart(frame, number):
#     fig = go.Figure(go.Bar(
#             x=frame.values.tolist(),
#             y=frame.index.tolist(),
#             orientation='h'))
#     fig.update_layout(
#         title=category_df.index[i])
#     filename = 'topCategoryNameBarChart'
#     py.plot(fig, filename=filename, auto_open=False)
#     print("Plotly Top Category Name Chart{}% Updated".format(number))
#     return filename

# def plotlyMonthlyChart(frame):
#     print('Updating Plotly Monthly Chart')
#     fig = go.Figure()
#     fig.add_trace(
#         go.Bar(
#             x = frame.index,
#             y = frame.amount
#         ))
#     fig.update_layout(title_text="Monthly Total Spending")
#     py.plot(fig, filename="HistoricalSpending", auto_open=False)
#     return 'Plotly Monthly Chart Updated'

# def plotlyCategoryHistory_Update(frame):
#     print('Updating Plotly Category History Chart')
#     fig = go.Figure()
#     fig.add_trace(
#         go.Bar(
#             y = frame.index,
#             x = frame.amount,
#             orientation='h'
#         ))
#     fig.update_layout(title_text="Historical Spending by Category")
#     py.plot(fig, filename="ALLMonthCategory.html", auto_open=False)
#     return 'Plotly Category History Chart Updated'

# def generate_HTML(balance_chase, balance_schwab, charts_tables, chase_total, schwab_total, cap1_total, balance_great_lakes, balance_cap_one, topCatHTML):
#     # Create the jinja2 environment.
#     # Notice the use of trim_blocks, which greatly helps control whitespace.
#     j2_env = Environment(loader=FileSystemLoader('./templates'),
#                          trim_blocks=True)
#     template_ready = j2_env.get_template('newhawk.html').render(
#         Date=today_str,
#         Chase_Balance=balance_chase,
#         Schwab_Balance=balance_schwab,
#         charts_and_tables=charts_tables,
#         Chase_Spent=chase_total,
#         Schwab_Spent=schwab_total,
#         Capital1_Spend=cap1_total,
#         Capital_One_Balance=balance_cap_one,
#         Great_Lakes_Balance=balance_great_lakes
#     )
#     return template_ready

# def blankHTMLchart(link):
#     template = (''
#     '<a href="{link}" target="_blank">' # Open the interactive graph when you click on the image
#         '<img src="{link}.png">'        # Use the ".png" magic url so that the latest, most-up-to-date image is included
#     '</a>'
#     '{link}'                              # Optional caption to include below the graph
#     '<br>'                                   # Line break
#     '<a href="{link}" style="color: rgb(190,190,190); text-decoration: none; font-weight: 200;" target="_blank">'
#         'Click to comment and see the interactive graph'  # Direct readers to Plotly for commenting, interactive graph
#     '</a>'
#     '<br>'
#     '<hr>'                                   # horizontal line
#     '')
#     return template
