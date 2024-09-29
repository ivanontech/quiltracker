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
    df = df.loc[df['Time_Diff_Minutes'] < 120]  # Filtering out differences larger than 120 minutes

    # Calculate Quil per hour
    df['Quil_Per_Hour'] = df['Quil_Per_Minute'] * 60  # Conversion to hours

    # Calculate earnings per hour in USD
    df['Earnings_Per_Hour'] = df['Quil_Per_Hour'] * wquil_price

    # Calculate hourly growth by grouping by 'Hour' and 'Peer ID'
    df['Hour'] = df['Date'].dt.floor('h')
    hourly_growth = df.groupby(['Peer ID', 'Hour'])['Balance'].last().reset_index()
    hourly_growth['Growth'] = hourly_growth.groupby('Peer ID')['Balance'].diff().fillna(0)

    # Calculate Quil per hour and earnings for each hour
    hourly_growth['Quil_Per_Hour'] = hourly_growth['Growth']  # Growth per hour
    hourly_growth['Earnings_USD'] = hourly_growth['Growth'] * wquil_price

    return df, hourly_growth

# Function to calculate rolling sum for the last X hours
def calculate_rolling_sum(hourly_growth_df, hours=24):
    hourly_growth_df = hourly_growth_df.copy()
    hourly_growth_df['Rolling_Quil_Per_Day'] = hourly_growth_df.groupby('Peer ID')['Growth'].rolling(window=hours, min_periods=1).sum().reset_index(level=0, drop=True)
    hourly_growth_df['Rolling_Earnings_Per_Day'] = hourly_growth_df.groupby('Peer ID')['Earnings_USD'].rolling(window=hours, min_periods=1).sum().reset_index(level=0, drop=True)
    return hourly_growth_df

# Calculate Quil earned in the last 24 hours
def calculate_last_24_hours(df):
    df['Date'] = pd.to_datetime(df['Date'])
    current_time = df['Date'].max()  # Get the latest timestamp
    start_time = current_time - timedelta(hours=25)  # Capture 25 hours instead of 24 for precision

    # Filter for data in the past 25 hours
    df_last_24_hours = df[df['Date'] >= start_time].copy()

    # Calculate the balance difference in the last 24 hours for each Peer ID
    last_24h_quil_per_day = df_last_24_hours.groupby('Peer ID')['Balance'].last() - df_last_24_hours.groupby('Peer ID')['Balance'].first()

    return last_24h_quil_per_day

# Calculate 24-hour Quil Per Hour
def calculate_last_24_hours_quil_per_hour(df):
    df['Date'] = pd.to_datetime(df['Date'])
    current_time = df['Date'].max()  # Get the latest timestamp
    start_time = current_time - timedelta(hours=24)

    # Filter for data in the past 24 hours
    df_last_24_hours = df[df['Date'] >= start_time].copy()

    # Calculate the balance difference in the last 24 hours for each Peer ID
    last_24h_quil_per_hour = df_last_24_hours.groupby('Peer ID')['Balance'].last() - df_last_24_hours.groupby('Peer ID')['Balance'].first()

    # Divide by 24 to get the per-hour average
    last_24h_quil_per_hour = last_24h_quil_per_hour / 24

    return last_24h_quil_per_hour

# Route to update balance data
@app.route('/update_balance', methods=['POST'])
def update_balance():
    try:
        data = request.get_json()
        print(f"Received data: {data}")

        if not data or 'peer_id' not in data or 'balance' not in data or 'timestamp' not in data:
            return 'Invalid data', 400

        peer_id = data['peer_id']
        balance = data['balance']
        timestamp = data['timestamp']

        # Skip writing to CSV if the balance is missing or invalid
        if balance == '' or pd.isna(balance):
            print(f"Invalid balance received for {peer_id}, skipping.")
            return 'Invalid balance', 400

        log_file = os.path.join(CSV_DIRECTORY, f'node_balance_{peer_id}.csv')

        if not os.path.exists(log_file):
            with open(log_file, 'w') as f:
                f.write('Date,Peer ID,Balance\n')

        with open(log_file, 'a') as f:
            f.write(f'{timestamp},{peer_id},{balance}\n')

        print(f"Logged balance for {peer_id}: {balance} at {timestamp}")
        return 'Balance updated', 200
    except Exception as e:
        print(f"Error updating balance: {e}")
        return 'Internal Server Error', 500

# Main dashboard route
@app.route('/')
def index():
    wquil_price = get_wquil_price()  # Fetch latest wQUIL price
    data_frames = []
    night_mode = request.args.get('night_mode', 'off')

    # Read and combine all CSV files
    for file_name in os.listdir(CSV_DIRECTORY):
        if file_name.endswith('.csv'):
            file_path = os.path.join(CSV_DIRECTORY, file_name)
            print(f"Reading CSV file: {file_path}")
            df = pd.read_csv(file_path)

            # Ensure 'Balance' is numeric, filter out non-numeric values
            df['Balance'] = pd.to_numeric(df['Balance'], errors='coerce')
            df = df.dropna(subset=['Balance'])  # Drop rows where Balance is NaN

            data_frames.append(df)

    # Combine all data into a single dataframe
    if data_frames:
        combined_df = pd.concat(data_frames)
        combined_df['Date'] = pd.to_datetime(combined_df['Date'])
        combined_df.sort_values('Date', inplace=True)

        # Remove duplicates and keep only the most recent balance for each Peer ID
        latest_balances = combined_df.groupby('Peer ID').last().reset_index()

        # Compute Quil earned per minute and hour
        combined_df, hourly_growth_df = compute_metrics(combined_df, wquil_price)

        # Calculate the rolling sum for the last 24 hours to get a live view
        hourly_growth_df = calculate_rolling_sum(hourly_growth_df, hours=24)

        # Fill missing values in latest_balances to prevent errors
        latest_balances['Balance'] = latest_balances['Balance'].fillna('')

        # Ensure the Peer IDs in last_24_hours_quil_per_day match the Peer IDs in latest_balances
        last_24_hours_quil_per_day = calculate_last_24_hours(combined_df).reindex(latest_balances['Peer ID']).fillna(0)
        latest_balances['24-Hour Quil Per Day'] = last_24_hours_quil_per_day.values

        # Ensure the Peer IDs in last_24_hours_quil_per_hour match the Peer IDs in latest_balances
        last_24_hours_quil_per_hour = calculate_last_24_hours_quil_per_hour(combined_df).reindex(latest_balances['Peer ID']).fillna(0)
        latest_balances['24-Hour Quil Per Hour'] = last_24_hours_quil_per_hour.values

        quil_per_minute = combined_df.groupby('Peer ID')['Quil_Per_Minute'].last()
        quil_per_hour = hourly_growth_df.groupby('Peer ID')['Quil_Per_Hour'].last()
        quil_per_day = hourly_growth_df.groupby('Peer ID')['Rolling_Quil_Per_Day'].last()

        dollar_per_hour = latest_balances['24-Hour Quil Per Hour'] * wquil_price
        dollar_per_day = latest_balances['24-Hour Quil Per Day'] * wquil_price

        status = []
        for peer_id in latest_balances['Peer ID']:
            current_quil_per_day = quil_per_day.get(peer_id, 0)
            last_24h_quil = last_24_hours_quil_per_day.get(peer_id, 0)
            if current_quil_per_day > last_24h_quil:
                status.append("Overperforming")
            elif current_quil_per_day < last_24h_quil:
                status.append("Underperforming")
            else:
                status.append("On Track")

        # Add computed values to the dataframe
        latest_balances['Quil Per Minute'] = quil_per_minute.values
        latest_balances['Quil Per Hour'] = quil_per_hour.values
        latest_balances['Quil Per Day'] = quil_per_day.values
        latest_balances['$ Per Hour'] = dollar_per_hour.values
        latest_balances['$ Per Day'] = dollar_per_day.values
        latest_balances['Status'] = status

        latest_balances = latest_balances.sort_values(by='Quil Per Day', ascending=False)

        # Calculate totals for the table footer
        total_quil_balance = latest_balances['Balance'].sum()
        total_quil_per_minute = latest_balances['Quil Per Minute'].sum()
        total_quil_per_hour = latest_balances['Quil Per Hour'].sum()
        total_24_hour_quil_per_hour = latest_balances['24-Hour Quil Per Hour'].sum()
        total_dollar_per_hour = latest_balances['$ Per Hour'].sum()
        total_quil_per_day = latest_balances['Quil Per Day'].sum()
        total_24_hour_quil_per_day = latest_balances['24-Hour Quil Per Day'].sum()
        total_dollar_per_day = latest_balances['$ Per Day'].sum()

        # Prepare data for rendering
        table_data = latest_balances[['Peer ID', 'Balance', 'Quil Per Day', '24-Hour Quil Per Day', 'Quil Per Minute', 'Quil Per Hour', '24-Hour Quil Per Hour', '$ Per Hour', '$ Per Day', 'Status']].to_dict(orient='records')

        # Generate Plotly charts
        balance_fig = px.line(combined_df, x='Date', y='Balance', color='Peer ID', title='Node Balances Over Time')
        quil_per_minute_fig = px.bar(combined_df, x='Date', y='Quil_Per_Minute', color='Peer ID', title='Quil Earned Per Minute')
        hourly_growth_fig = px.area(hourly_growth_df, x='Hour', y='Growth', color='Peer ID', title='Hourly Growth in Quil')
        earnings_per_hour_fig = px.bar(hourly_growth_df, x='Hour', y='Earnings_USD', color='Peer ID', title='Earnings in USD per Hour')

        chart_template = 'plotly_dark' if night_mode == 'on' else 'plotly'
        balance_fig.update_layout(template=chart_template)
        quil_per_minute_fig.update_layout(template=chart_template)
        hourly_growth_fig.update_layout(template=chart_template)
        earnings_per_hour_fig.update_layout(template=chart_template)

        # Convert charts to HTML
        balance_graph_html = balance_fig.to_html(full_html=False)
        quil_minute_graph_html = quil_per_minute_fig.to_html(full_html=False)
        hourly_growth_graph_html = hourly_growth_fig.to_html(full_html=False)
        earnings_per_hour_graph_html = earnings_per_hour_fig.to_html(full_html=False)
    else:
        # Default empty values
        table_data = []
        total_quil_balance = total_quil_per_minute = total_quil_per_hour = total_24_hour_quil_per_hour = 0
        total_dollar_per_hour = total_quil_per_day = total_24_hour_quil_per_day = total_dollar_per_day = 0
        balance_graph_html = quil_minute_graph_html = hourly_growth_graph_html = earnings_per_hour_graph_html = ""

    # Render the index.html page with the computed data
    return render_template('index.html', table_data=table_data,
                           total_balance=total_quil_balance,
                           total_quil_per_minute=total_quil_per_minute,
                           total_quil_per_hour=total_quil_per_hour,
                           total_24_hour_quil_per_hour=total_24_hour_quil_per_hour,
                           total_dollar_per_hour=total_dollar_per_hour,
                           total_quil_per_day=total_quil_per_day,
                           total_24_hour_quil_per_day=total_24_hour_quil_per_day,
                           total_dollar_per_day=total_dollar_per_day,
                           balance_graph_html=balance_graph_html,
                           quil_minute_graph_html=quil_minute_graph_html,
                           hourly_growth_graph_html=hourly_growth_graph_html,
                           earnings_per_hour_graph_html=earnings_per_hour_graph_html,
                           wquil_price=wquil_price,
                           night_mode=night_mode)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
