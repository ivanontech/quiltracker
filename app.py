import pandas as pd
import plotly.express as px
import os
import requests
from flask import Flask, render_template, request
from datetime import timedelta

app = Flask(__name__)

# Path to the directory where CSV files are stored
CSV_DIRECTORY = "/root/quiltracker"

# Disable caching for browser
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Function to get the latest price of Wrapped Quil (wQUIL) from CoinGecko
def get_wquil_price():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        'ids': 'wrapped-quil',
        'vs_currencies': 'usd'
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        return data['wrapped-quil']['usd']
    except Exception as e:
        print(f"Error fetching wQUIL price: {e}")
        return 0

# Compute Quil earned per minute, per hour, and earnings
def compute_metrics(df, wquil_price):
    df['Date'] = pd.to_datetime(df['Date'])
    df['Balance'] = df['Balance'].astype(float)

    # Calculate Quil earned per minute
    df['Time_Diff_Minutes'] = df.groupby('Peer ID')['Date'].diff().dt.total_seconds() / 60
    df['Quil_Per_Minute'] = df.groupby('Peer ID')['Balance'].diff() / df['Time_Diff_Minutes']
    df['Quil_Per_Minute'] = df['Quil_Per_Minute'].fillna(0)

    # Filter out large time gaps to avoid incorrect calculations
    df = df.loc[df['Time_Diff_Minutes'] < 120]

    # Calculate Quil per hour
    df['Quil_Per_Hour'] = df['Quil_Per_Minute'] * 60

    # Calculate earnings per hour in USD
    df['Earnings_Per_Hour'] = df['Quil_Per_Hour'] * wquil_price

    # Calculate hourly growth by grouping by 'Hour' and 'Peer ID'
    df['Hour'] = df['Date'].dt.floor('h')
    hourly_growth = df.groupby(['Peer ID', 'Hour'])['Balance'].last().reset_index()
    hourly_growth['Growth'] = hourly_growth.groupby('Peer ID')['Balance'].diff().fillna(0)

    # Calculate Quil per hour and earnings for each hour
    hourly_growth['Quil_Per_Hour'] = hourly_growth['Growth']
    hourly_growth['Earnings_USD'] = hourly_growth['Growth'] * wquil_price

    return df, hourly_growth

# Function to calculate Quil earned in the last 1,440 minutes (24 hours)
def calculate_last_1440_minutes(df):
    df = df.sort_values('Date')
    last_1440_values = df.groupby('Peer ID').tail(1440)
    last_1440_quil_per_day = last_1440_values.groupby('Peer ID')['Balance'].last() - last_1440_values.groupby('Peer ID')['Balance'].first()
    return last_1440_quil_per_day

# Calculate 24-hour Quil Per Hour based on the last 1,440 minutes
def calculate_last_1440_minutes_quil_per_hour(df):
    df = df.sort_values('Date')
    last_1440_values = df.groupby('Peer ID').tail(1440)
    last_1440_quil_per_hour = (last_1440_values.groupby('Peer ID')['Balance'].last() - last_1440_values.groupby('Peer ID')['Balance'].first()) / 24
    return last_1440_quil_per_hour

# Route to update balance data
@app.route('/update_balance', methods=['POST'])
def update_balance():
    try:
        data = request.get_json()
        print(f"Received data: {data}")

        required_fields = {'peer_id', 'version', 'max_frame', 'prover_ring', 'seniority', 'balance', 'timestamp'}
        if not data or not required_fields.issubset(data):
            return 'Invalid data', 400

        peer_id = data['peer_id']
        version = data['version']
        max_frame = data['max_frame']
        prover_ring = data['prover_ring']
        seniority = data['seniority']
        balance = data['balance']
        timestamp = data['timestamp']

        log_file = os.path.join(CSV_DIRECTORY, f'node_balance_{peer_id}.csv')

        if not os.path.exists(log_file):
            with open(log_file, 'w') as f:
                f.write('Date,Peer ID,Version,Max Frame,Prover Ring,Seniority,Balance\n')

        with open(log_file, 'a') as f:
            f.write(f'{timestamp},{peer_id},{version},{max_frame},{prover_ring},{seniority},{balance}\n')

        print(f"Logged balance for {peer_id}: {balance} at {timestamp}")
        return 'Balance updated', 200
    except Exception as e:
        print(f"Error updating balance: {e}")
        return 'Internal Server Error', 500

# Main dashboard route
@app.route('/')
def index():
    wquil_price = get_wquil_price()
    data_frames = []
    night_mode = request.args.get('night_mode', 'off')

    # Read and combine all CSV files, skipping lines with errors
    for file_name in os.listdir(CSV_DIRECTORY):
        if file_name.endswith('.csv'):
            file_path = os.path.join(CSV_DIRECTORY, file_name)
            print(f"Reading CSV file: {file_path}")
            try:
                df = pd.read_csv(file_path, on_bad_lines='skip')  # Skip problematic lines
                if df['Balance'].dtype == 'object':
                    df['Balance'] = df['Balance'].str.extract(r'([\d\.]+)').astype(float)
                data_frames.append(df)
            except pd.errors.ParserError as e:
                print(f"Error reading {file_path}: {e}")
                continue

    if data_frames:
        combined_df = pd.concat(data_frames)
        combined_df['Date'] = pd.to_datetime(combined_df['Date'])
        combined_df.sort_values('Date', inplace=True)

        # Remove duplicates and keep only the most recent balance for each Peer ID
        latest_balances = combined_df.groupby('Peer ID').last().reset_index()

        # Compute Quil earned per minute and hour
        combined_df, hourly_growth_df = compute_metrics(combined_df, wquil_price)

        # Calculate Quil earned in the last 24 hours (1,440 records)
        last_1440_quil_per_day = calculate_last_1440_minutes(combined_df)
        last_1440_quil_per_hour = calculate_last_1440_minutes_quil_per_hour(combined_df)

        # Reindex to match lengths of latest_balances and last 1,440 minute data
        latest_balances = latest_balances.set_index('Peer ID')
        last_1440_quil_per_day = last_1440_quil_per_day.reindex(latest_balances.index)
        last_1440_quil_per_hour = last_1440_quil_per_hour.reindex(latest_balances.index)

        # Add 24-Hour Quil Per Hour and 24-Hour Quil Per Day to latest_balances
        latest_balances['24-Hour Quil Per Day'] = last_1440_quil_per_day.fillna(0).values
        latest_balances['24-Hour Quil Per Hour'] = last_1440_quil_per_hour.fillna(0).values

        # Convert to numeric to avoid further issues
        latest_balances['24-Hour Quil Per Hour'] = pd.to_numeric(latest_balances['24-Hour Quil Per Hour'], errors='coerce').fillna(0)
        latest_balances['24-Hour Quil Per Day'] = pd.to_numeric(latest_balances['24-Hour Quil Per Day'], errors='coerce').fillna(0)

        # Calculate Quil per minute, per hour, and per day
        quil_per_minute = combined_df.groupby('Peer ID')['Quil_Per_Minute'].last()
        quil_per_hour = hourly_growth_df.groupby('Peer ID')['Quil_Per_Hour'].last()
        quil_per_day = hourly_growth_df.groupby('Peer ID')['Growth'].sum()

        # Reindex to align with latest_balances and fill missing values
        quil_per_minute = quil_per_minute.reindex(latest_balances.index).fillna(0)
        quil_per_hour = quil_per_hour.reindex(latest_balances.index).fillna(0)
        quil_per_day = quil_per_day.reindex(latest_balances.index).fillna(0)

        # Calculate dollar amounts based on 24-hour Quil Per Hour
        dollar_per_hour = latest_balances['24-Hour Quil Per Hour'] * wquil_price
        dollar_per_day = latest_balances['24-Hour Quil Per Day'] * wquil_price

        # Fill any NaN values in 'dollar_per_hour' and 'dollar_per_day' with 0
        dollar_per_hour = dollar_per_hour.fillna(0)
        dollar_per_day = dollar_per_day.fillna(0)

        # Ensure all required columns are present in latest_balances
        columns = ['Balance', 'Max Frame', 'Prover Ring', 'Seniority', 'Quil Per Day', '24-Hour Quil Per Day', 'Quil Per Minute', 'Quil Per Hour', '24-Hour Quil Per Hour', '$ Per Hour', '$ Per Day']
        for col in columns:
            if col not in latest_balances.columns:
                latest_balances[col] = 0  # Fill missing columns with default value of 0

        # Prepare table data for rendering
        table_data = latest_balances[columns].reset_index()

        # Plot: Node Balances Over Time
        balance_fig = px.line(combined_df, x='Date', y='Balance', color='Peer ID', title='Node Balances Over Time')
        quil_per_minute_fig = px.bar(combined_df, x='Date', y='Quil_Per_Minute', color='Peer ID', title='Quil Earned Per Minute')
        hourly_growth_fig = px.area(hourly_growth_df, x='Hour', y='Growth', color='Peer ID', title='Hourly Growth in Quil')
        earnings_per_hour_fig = px.bar(hourly_growth_df, x='Hour', y='Earnings_USD', color='Peer ID', title='Earnings in USD per Hour')

        chart_template = 'plotly_dark' if night_mode == 'on' else 'plotly'
        balance_fig.update_layout(template=chart_template)
        quil_per_minute_fig.update_layout(template=chart_template)
        hourly_growth_fig.update_layout(template=chart_template)
        earnings_per_hour_fig.update_layout(template=chart_template)

        # Convert Plotly figures to HTML for rendering
        balance_graph_html = balance_fig.to_html(full_html=False)
        quil_minute_graph_html = quil_per_minute_fig.to_html(full_html=False)
        hourly_growth_graph_html = hourly_growth_fig.to_html(full_html=False)
        earnings_per_hour_graph_html = earnings_per_hour_fig.to_html(full_html=False)
    else:
        table_data = []
        total_quil_balance = total_quil_per_minute = total_quil_per_hour = total_24_hour_quil_per_hour = 0
        total_dollar_per_hour = total_quil_per_day = total_24_hour_quil_per_day = total_dollar_per_day = 0
        balance_graph_html = quil_minute_graph_html = hourly_growth_graph_html = earnings_per_hour_graph_html = ""

    return render_template('index.html', table_data=table_data,
                           total_balance=latest_balances['Balance'].sum(),
                           total_quil_per_minute=latest_balances['Quil Per Minute'].sum(),
                           total_quil_per_hour=latest_balances['Quil Per Hour'].sum(),
                           total_24_hour_quil_per_hour=latest_balances['24-Hour Quil Per Hour'].sum(),
                           total_dollar_per_hour=dollar_per_hour.sum(),
                           total_quil_per_day=latest_balances['Quil Per Day'].sum(),
                           total_24_hour_quil_per_day=latest_balances['24-Hour Quil Per Day'].sum(),
                           total_dollar_per_day=dollar_per_day.sum(),
                           balance_graph_html=balance_graph_html,
                           quil_minute_graph_html=quil_minute_graph_html,
                           hourly_growth_graph_html=hourly_growth_graph_html,
                           earnings_per_hour_graph_html=earnings_per_hour_graph_html,
                           wquil_price=wquil_price,
                           night_mode=night_mode)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
