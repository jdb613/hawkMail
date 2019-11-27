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
import locale
from scipy import stats
import numpy as np
import re

locale.setlocale( locale.LC_ALL, '' )

today_str = str(date.today())
hawk_mode = str(os.getenv('HAWK_MODE'))


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
    print('Start of Month: ', month_start)
    print('Start of Month Type: ', type(month_start))
    return(month_start)



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
            df = df.loc[df.pending == False]
        except:
            print('cant flatten: ', type(d))
            print(d)
            df = pd.DataFrame()


    return df

def pandaSum(frame):
    fsum = frame['amount'].sum()
    sum_str = f'{fsum:.2f}'
    return '$' + sum_str

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
    monthly_sum = df.resample('M', loffset=pd.Timedelta(16, 'd')).sum()
    return monthly_sum

def getData(environment, exclusions):
    master_data = {}
    tokens = plaidTokens()
    today_str = str(date.today())

    if environment == 'sandbox':
        start_date = date.today().replace(year = date.today().year - 2).strftime('%Y-%m-%d')
        trnsx_chase, master_data['balance_chase'] = getTransactions(SANDBOXplaidClient(), tokens['Chase']['sandbox'], start_date, today_str)
        trnsx_schwab, master_data['balance_schwab'] = getTransactions(SANDBOXplaidClient(), tokens['Schwab']['sandbox'], start_date, today_str)
        cap1_response = cap1_lakes_get(SANDBOXplaidClient(), tokens['Capital_One']['sandbox'], start_date, today_str)
        lakes_response = cap1_lakes_get(SANDBOXplaidClient(), tokens['Great_Lakes']['sandbox'], start_date, today_str)

    elif environment == 'testing':
        start_date = date.today() - timedelta(days=30)
        trnsx_chase, master_data['balance_chase'] = getTransactions(plaidClient(), tokens['Chase']['access_token'], start_date.strftime('%Y-%m-%d'), today_str)
        trnsx_schwab, master_data['balance_schwab'] = getTransactions(plaidClient(), tokens['Schwab']['access_token'], start_date.strftime('%Y-%m-%d'), today_str)
        cap1_response = cap1_lakes_get(plaidClient(), tokens['Capital_One']['access_token'], start_date.strftime('%Y-%m-%d'), today_str)
        lakes_response = cap1_lakes_get(plaidClient(), tokens['Great_Lakes']['access_token'], start_date.strftime('%Y-%m-%d'), today_str)


    elif environment == 'production':
        start_date = date.today().replace(year = date.today().year - 2).strftime('%Y-%m-%d')
        trnsx_chase, master_data['balance_chase'] = getTransactions(plaidClient(), tokens['Chase']['access_token'], start_date, today_str)
        trnsx_schwab, master_data['balance_schwab'] = getTransactions(plaidClient(), tokens['Schwab']['access_token'], start_date, today_str)
        cap1_response = cap1_lakes_get(plaidClient(), tokens['Capital_One']['access_token'], start_date, today_str)
        lakes_response = cap1_lakes_get(plaidClient(), tokens['Great_Lakes']['access_token'], start_date, today_str)

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

def cumulativeSum(data, date, exclusions, hawk_mode):
    df = json2pandaClean(data, exclusions)
    month_trnsx = df.loc[df.index >= date]
    month_trnsx1 = month_trnsx.resample('D')['amount'].sum().reset_index()
    month_trnsx1['CUMSUM'] = month_trnsx1['amount'].cumsum()
    month_trnsx1 = month_trnsx1.set_index('date')
    print('Updating Plotly Cumulative Chart')
    fig = go.Figure(
        data=[
            go.Scatter(name='Cumulative Spending', x=month_trnsx1.index.tolist(), y=month_trnsx1.CUMSUM.tolist(), yaxis="y2"),
            go.Bar(name='Daily Spend', x=month_trnsx1.index.tolist(), y=month_trnsx1.amount.tolist(),
                text = [str('<b>' + locale.currency(i) + '</b>') for i in month_trnsx1.amount.tolist()],
                textposition='auto',
                    textfont=dict(
                    color="yellow"
                    ))
        ],
        layout=go.Layout(
            title=go.layout.Title(text="Cumulative Spending")
        ))
    fig.update_xaxes(nticks=len(month_trnsx1), tickangle=45)
    fig.update_layout(
            yaxis=dict(
                title="Daily Spend",
                titlefont=dict(
                    color="#d50301"
                    ),
            tickfont=dict(
                    color="#d50301"
                )
            ),
            yaxis2=dict(
                title="Cumulative Spending",
                titlefont=dict(
                    color="#0400fb"
                ),
                tickfont=dict(
                    color="#0400fb"
                ),
                anchor="x",
                overlaying="y",
                side="right"
            ))
    try:
        if hawk_mode == 'sandbox':
            fig.show()
            URL = 'Sandbox'
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
    sum_frame = drop_columns(sum_frame)
    sum_frame = tidy_df(sum_frame, hawk_mode)
    print('Sum_frame: ', sum_frame)
    if hawk_mode == 'sandbox':
        client = SANDBOXplaidClient()
        chase_acts = [account['account_id'] for account in client.Accounts.get(tokens['Chase']['sandbox'])['accounts']]
        schwab_acts = [account['account_id'] for account in client.Accounts.get(tokens['Schwab']['sandbox'])['accounts']]
        all_acts = chase_acts + schwab_acts
        chase_frame = sum_frame[sum_frame['account'].isin(chase_acts)]
        print('chase_frame: ', chase_frame)
        schwab_frame = sum_frame[sum_frame['account'].isin(schwab_acts)]
        both_frames = sum_frame[sum_frame['account'].isin(all_acts)]
        print('Monthly Spending Both Frames Size: ', both_frames.describe())
    else:
        client = plaidClient()

        chase_frame = sum_frame[sum_frame['account'].isin(chase_names)]
        print('chase_frame: ', chase_frame)
        schwab_frame = sum_frame[sum_frame['account'].isin(schwab_names)]
        both_frames = sum_frame[sum_frame['account'].isin(all_names)]
        print('Monthly Spending Both Frames Size: ', both_frames.describe())

    Smonthly_sum = schwab_frame.resample('M', loffset=pd.Timedelta(16, 'd')).sum()
    Cmonthly_sum = chase_frame.resample('M', loffset=pd.Timedelta(16, 'd')).sum()
    both_frames = both_frames.resample('M', loffset=pd.Timedelta(16, 'd')).sum()
    print('Resample Monthly Spending Both Frames Size: ', both_frames.describe())
    cc_payments = paymentFinder(json)
    print('cc_payments type : ', type(cc_payments))
    print('cc_payments 0 : ', cc_payments.iloc[0].amount)
    #Cmonthly_sum = Cmonthly_sum.drop(columns=['category'])
    #Smonthly_sum = Smonthly_sum.drop(columns=['category'])
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
        fig.update_xaxes(nticks=len(Cmonthly_sum), tickangle=45)
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
                    y1=cc_payments.iloc[i].amount,
                    line=dict(
                        color="LightSeaGreen",
                        width=5,
                        dash="dashdot",
                    ),
            ))
        fig.update_shapes(dict(xref='x', yref='y'))
        if hawk_mode == 'sandbox':
            fig.show()
            URL = 'Sandbox'
        else:
            URL = py.plot(fig, filename="monthly_spending", auto_open=False)
    else:
        if hawk_mode == 'sandbox':
            URL = 'Sandbox'
        else:
            URL = 'Update Not Requested'
    return both_frames, URL

def progress(json, date, exclusions, hawk_mode):
    lcl_df = json2pandaClean(json, exclusions)
    monthly_spending_df, URL = monthlySpending(json, exclusions, hawk_mode, 'No')
    print('Monthly Spending')
    print(monthly_spending_df)
    three_mnth_trailing = monthly_spending_df[-3:]
    print('3 Month Trailing')
    print(three_mnth_trailing)
    threeMave = three_mnth_trailing.mean()
    this_month_df = lcl_df.loc[date:]
    dec = this_month_df['amount'].sum()/threeMave * 100
    dec_rez = dec['amount']
    pct = f'{dec_rez:.2f}' + '%'
    return pct

def curMonthCategories(data, date, exclusions, hawk_mode):
    df1 = json2pandaClean(data, exclusions)
    cat_df = df1.loc[df1.index >= date]
    cat_df = cat_df.groupby('category_1')["amount"].sum()
    df_fram = cat_df.to_frame()
    df_fram = df_fram[-15:].sort_values(by='amount', ascending=True)
    print('Updating Plotly Category Chart')
    fig = go.Figure(
        data = [
            go.Bar(
                name="Category Spend",
                y=df_fram.index.tolist(),
                x=df_fram.amount.values.tolist(),
                marker=dict(
                color='#4A707A',
                line=dict(
                    color='green',
                    width=1),
                    ),
                orientation='h')
            ],
        layout=go.Layout(
            title=go.layout.Title(text="This Month's Spending by Category")
        ))
    annotations = []
    for yd, xd in zip(df_fram.index.tolist(), df_fram.amount.values.tolist()):
        annotations.append(dict(xref='x1', yref='y1',
                                y=yd, x=xd + 100,
                                text=locale.currency(xd),
                                font=dict(family='Arial', size=12,
                                        color='rgb(50, 171, 96)'),
                                showarrow=False))
    fig.update_layout(annotations=annotations)
    if hawk_mode == 'sandbox':
        fig.show()
        URL = 'Sandbox'
    else:
        URL = py.plot(fig, filename="CurrentMonthCategory", auto_open=False)
    return URL

def topCategoryName(data, date, exclusions, hawk_mode):
    HTML = []
    frame = json2pandaClean(data, exclusions)
    frame = drop_columns(frame)
    frame = tidy_df(frame, hawk_mode)
    frame = frame.loc[date:]
    category_df = frame.groupby('category_0')['amount'].sum().nlargest(5)
    print('Category DF: ', category_df)
    for i in range(len(category_df)):

        cat_data = frame[frame['category_0'] == category_df.index[i]]

        plt_data = cat_data.groupby('name')['amount'].sum().sort_values()[-25:]
        print('Updating Top Category Name Chart {}%'.format(i))
        fig = go.Figure(go.Bar(
                x=[locale.currency(j) for j in plt_data.values.tolist()],
                y=plt_data.index.tolist(),
                orientation='h'))
        fig.update_layout(
            title=category_df.index[i])
        filename = 'topCategoryNameBarChart' + str(i)
        if hawk_mode == 'sandbox':
            fig.show()
            URL = 'Sandbox'
        else:
            URL = py.plot(fig, filename=filename, auto_open=False)
    return URL




def categoryHistory(data, exclusions, hawk_mode):
    df1 = json2pandaClean(data, exclusions)
    cat_df = df1.groupby('category_1')["amount"].sum()
    df_fram = cat_df.to_frame()
    df_fram = df_fram[-15:].sort_values(by='amount', ascending=True)

    print('Updating Plotly Category Chart')
    fig = go.Figure(
        data = [
            go.Bar(
                name="Category Spend Historically",
                y=df_fram.index.tolist(),
                x=df_fram.amount.values.tolist(),
                marker=dict(
                color='rgba(58, 71, 80, 0.6)',
                line=dict(
                    color='rgba(58, 71, 80, 0.6)',
                    width=1),
                    ),
                orientation='h')
            ],
        layout=go.Layout(
            title=go.layout.Title(text="This Month's Spending by Category")
        ))
    annotations = []
    for yd, xd in zip(df_fram.index.tolist(), df_fram.amount.values.tolist()):
        annotations.append(dict(xref='x1', yref='y1',
                                y=yd, x=xd + 100,
                                text=locale.currency(xd),
                                font=dict(family='Arial', size=12,
                                        color='rgb(50, 171, 96)'),
                                showarrow=False))
    fig.update_layout(annotations=annotations)
    if hawk_mode == 'sandbox':
        fig.show()
        URL = 'Sandbox'
    else:
        URL = py.plot(fig, filename="CurrentMonthCategory", auto_open=False)

    return df_fram.sort_values(by='category_1', ascending=True), URL

def relativeCategories(data, date, exclusions, hawk_mode):
    df1 = json2pandaClean(data, exclusions)
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

    fig = go.Figure()
    fig.add_trace(go.Bar(x=comb.index.tolist(),
                    y=comb['This Month'].tolist(),
                    name='This Month',
                    marker_color='rgb(55, 83, 109)'
                    ))
    fig.add_trace(go.Bar(x=comb.index.tolist(),
                    y=comb['Average'].tolist(),
                    name='Average',
                    marker_color='rgb(26, 118, 255)'
                    ))

    fig.update_layout(
        title='Relative Category Spending',
        xaxis_tickfont_size=14,
        yaxis=dict(
            title='Spent',
            titlefont_size=16,
            tickfont_size=14,
        ),
        legend=dict(
            x=0,
            y=1.0,
            bgcolor='rgba(255, 255, 255, 0)',
            bordercolor='rgba(255, 255, 255, 0)'
        ),
        barmode='group',
        bargap=0.15, # gap between bars of adjacent location coordinates.
        bargroupgap=0.1 # gap between bars of the same location coordinate.
    )
    if hawk_mode == 'sandbox':
            fig.show()
            URL = 'sandbox'
    else:
        URL = py.plot(fig, filename="RelativeCategory", auto_open=False)
    return URL






########## Plotly Charts ########

def plotlyTopCategoryNameChart(frame, number):
    fig = go.Figure(go.Bar(
            x=frame.values.tolist(),
            y=frame.index.tolist(),
            orientation='h'))
    fig.update_layout(
        title=category_df.index[i])
    filename = 'topCategoryNameBarChart'
    py.plot(fig, filename=filename, auto_open=False)
    print("Plotly Top Category Name Chart{}% Updated".format(number))
    return filename

def plotlyMonthlyChart(frame):
    print('Updating Plotly Monthly Chart')
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x = frame.index,
            y = frame.amount
        ))
    fig.update_layout(title_text="Monthly Total Spending")
    py.plot(fig, filename="HistoricalSpending", auto_open=False)
    return 'Plotly Monthly Chart Updated'

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

def pendingTable(data, exclusions):
    df = json2pandaClean(data, exclusions)
    df = df.loc[df.pending == True]
    df = drop_columns(df)
    df = tidy_df(df, hawk_mode)
    df = df.sort_index()


    data_in_html = df.to_html(index=True)
    total_id = 'totalID'
    header_id = 'headerID'
    style_in_html = """<style>
        table#{total_table} {{color='black';font-size:13px; text-align:center; border:0.2px solid black;
                            border-collapse:collapse; table-layout:fixed; height="250"; text-align:center }}
        thead#{header_table} {{background-color: #4D4D4D; color:#ffffff}}
        </style>""".format(total_table=total_id, header_table=header_id)
    data_in_html = re.sub(r'<table', r'<table id=%s ' % total_id, data_in_html)
    data_in_html = re.sub(r'<thead', r'<thead id=%s ' % header_id, data_in_html)

    return data_in_html

def monthsTransactionTable(data, date, exclusions, hawk_mode):
    df = json2pandaClean(data, exclusions)
    df = df.loc[df.pending == False]
    df = drop_columns(df)
    df = tidy_df(df, hawk_mode)
    df = df.sort_index()

    try:
        print('filtered df', df.loc[df.index >= str(date)])
        df = df.loc[df.index >= str(date)]
    except Exception as e:
        print('date troubleshooting:')
        print(e)

    data_in_html = df.to_html(index=True)
    total_id = 'totalID'
    header_id = 'headerID'
    style_in_html = """<style>
        table#{total_table} {{color='black';font-size:13px; text-align:center; border:0.2px solid black;
                            border-collapse:collapse; table-layout:fixed; height="250"; text-align:center }}
        thead#{header_table} {{background-color: #4D4D4D; color:#ffffff}}
        </style>""".format(total_table=total_id, header_table=header_id)
    data_in_html = re.sub(r'<table', r'<table id=%s ' % total_id, data_in_html)
    data_in_html = re.sub(r'<thead', r'<thead id=%s ' % header_id, data_in_html)

    return data_in_html

def chartLINK(filename):
    try:
        url = py.plot(fig, filename=c)
        return url.resource
    except:
        return 'Link Not Found'


def tableChartHTML(data, date, exclusions, hawk_mode, chart_files):
    chartsHTML = ''
    for c in chart_files:
        chart_link = chartLINK(c)
        chartHTML = htmlGraph(chart_link)
        chartsHTML += chartHTML
        if 'topCategoryNameBarChart' in c and hawk_mode != 'sandbox':

            frame = json2pandaClean(data, exclusions)
            frame = drop_columns(frame)
            frame = tidy_df(frame, hawk_mode)
            frame = frame.loc[date:]
            category_df = frame.groupby('category_0')['amount'].sum().nlargest(5)

            fig = py.get_figure(c)
            title = fig['layout']['title']
            cat_data = frame[frame['category_0'] == title]

            plt_data = cat_data.groupby('name')['amount'].sum().sort_values()
            header = '<h2>' + str(title) + '</h2>'
            chartHTML += header
            html_data = plt_data.to_frame().nlargest(5, 'amount')
            df_html_output = html_data.to_html().replace('<th>','<th style = "background-color: grey">')
            chartsHTML += df_html_output

        # print('Chart HTML: ', chartsHTML)
        # body = '\r\n\n<br>'.join('%s'%item for item in chartsHTML)
        # print('Body: ', body)

    return chartsHTML

def blankHTMLchart(link):
    template = (''
    '<a href="{link}" target="_blank">' # Open the interactive graph when you click on the image
        '<img src="{link}.png">'        # Use the ".png" magic url so that the latest, most-up-to-date image is included
    '</a>'
    '{link}'                              # Optional caption to include below the graph
    '<br>'                                   # Line break
    '<a href="{link}" style="color: rgb(190,190,190); text-decoration: none; font-weight: 200;" target="_blank">'
        'Click to comment and see the interactive graph'  # Direct readers to Plotly for commenting, interactive graph
    '</a>'
    '<br>'
    '<hr>'                                   # horizontal line
    '')
    return template

def htmlGraph(graph):
    print('Graph Data for HTML: ', graph)
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
    print('Graph TEST: ', graph)
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


def generate_HTML(balance_chase, balance_schwab, charts_tables, chase_total, schwab_total, cap1_total, balance_great_lakes, balance_cap_one, topCatHTML):
    # Create the jinja2 environment.
    # Notice the use of trim_blocks, which greatly helps control whitespace.
    j2_env = Environment(loader=FileSystemLoader('./templates'),
                         trim_blocks=True)
    template_ready = j2_env.get_template('newhawk.html').render(
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

def jinjaTEST(data):
    j2_env = Environment(loader=FileSystemLoader('./templates'),
                         trim_blocks=True)
    template_ready = j2_env.get_template('newhawk.html').render(
        jinja_data=data
    )

    return template_ready

def emailPreview(mail):
    prev = open('templates/email_preview.html','w')
    prev.write(mail)
    prev.close()
