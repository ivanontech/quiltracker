from flask import Flask, request, render_template
import pandas as pd
import plotly.express as px
import os
import requests
from datetime import timedelta

app = Flask(__name__)

# Path to the directory where CSV files are stored
CSV_DIRECTORY = "/root/quiltracker"

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

# Updated function to calculate Quil earned in the last 24 hours
def calculate_last_24_hours(df):
    df['Date'] = pd.to_datetime(df['Date'])
    current_time = df['Date'].max()  # Get the latest timestamp
    start_time = current_time - timedelta(hours=25)  # Capture 25 hours instead of 24 for precision
    
    # Filter for data in the past 25 hours
    df_last_24_hours = df[df['Date'] >= start_time].copy()

    # Calculate the balance difference in the last 24 hours for each Peer ID
    last_24h_quil_per_day = df_last_24_hours.groupby('Peer ID')['Balance'].last() - df_last_24_hours.groupby('Peer ID')['Balance'].first()
    
    return last_24h_quil_per_day

# New function to calculate 24-hour Quil Per Hour
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

@app.route('/')
def index():
    wquil_price = get_wquil_price()  # Fetch the current price of wQUIL
    data_frames = []
    night_mode = request.args.get('night_mode', 'off')  # Get night mode from query parameter

    # Read and combine all CSV files
    for file_name in os.listdir(CSV_DIRECTORY):
        if file_name.endswith('.csv'):
            file_path = os.path.join(CSV_DIRECTORY, file_name)
            df = pd.read_csv(file_path)

            # Check if the balance column contains string values
            if df['Balance'].dtype == 'object':
                df['Balance'] = df['Balance'].str.extract(r'([\d\.]+)').astype(float)

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

        # Ensure that 'Balance' values are correctly filled with an empty string instead of 0
        latest_balances['Balance'] = latest_balances['Balance'].fillna('')  # Fill missing balances with an empty string

        # Handle case where 24-Hour Quil Per Day might be missing or 0
        last_24_hours_quil_per_day = calculate_last_24_hours(combined_df)
        latest_balances['24-Hour Quil Per Day'] = last_24_hours_quil_per_day.fillna('').values  # If NaN, it defaults to an empty string

        # Add 24-Hour Quil Per Hour calculation
        last_24_hours_quil_per_hour = calculate_last_24_hours_quil_per_hour(combined_df)
        latest_balances['24-Hour Quil Per Hour'] = last_24_hours_quil_per_hour.fillna('').values  # If NaN, it defaults to an empty string

        # Calculate Quil per minute, per hour, and per day for each Peer ID
        quil_per_minute = combined_df.groupby('Peer ID')['Quil_Per_Minute'].last()
        quil_per_hour = hourly_growth_df.groupby('Peer ID')['Quil_Per_Hour'].last()
        quil_per_day = hourly_growth_df.groupby('Peer ID')['Rolling_Quil_Per_Day'].last()

        # Calculate dollar amounts based on 24-hour Quil Per Hour
        dollar_per_hour = latest_balances['24-Hour Quil Per Hour'] * wquil_price
        dollar_per_day = latest_balances['24-Hour Quil Per Day'] * wquil_price

        # Determine the status (Overperforming, Underperforming, On Track)
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

        latest_balances['Quil Per Minute'] = quil_per_minute.values
        latest_balances['Quil Per Hour'] = quil_per_hour.values
        latest_balances['Quil Per Day'] = quil_per_day.values
        latest_balances['$ Per Hour'] = dollar_per_hour.values
        latest_balances['$ Per Day'] = dollar_per_day.values
        latest_balances['Status'] = status  # Add status column

        # Sort by Quil Per Day in descending order
        latest_balances = latest_balances.sort_values(by='Quil Per Day', ascending=False)

        # Sum for the totals row
        total_quil_balance = latest_balances['Balance'].sum()
        total_quil_per_minute = latest_balances['Quil Per Minute'].sum()
        total_quil_per_hour = latest_balances['Quil Per Hour'].sum()
        total_24_hour_quil_per_hour = latest_balances['24-Hour Quil Per Hour'].sum()
        total_dollar_per_hour = latest_balances['$ Per Hour'].sum()
        total_quil_per_day = latest_balances['Quil Per Day'].sum()
        total_24_hour_quil_per_day = latest_balances['24-Hour Quil Per Day'].sum()
        total_dollar_per_day = latest_balances['$ Per Day'].sum()

        # Data for the table (with Quil Per Hour, Quil Per Minute, Quil Per Day, and Status)
        table_data = latest_balances[['Peer ID', 'Balance', 'Quil Per Day', '24-Hour Quil Per Day', 'Quil Per Minute', 'Quil Per Hour', '24-Hour Quil Per Hour', '$ Per Hour', '$ Per Day', 'Status']]

        # Convert to list of dictionaries for easy templating
        table_data = table_data.to_dict(orient='records')

        # Plot: Node Balances Over Time
        balance_fig = px.line(combined_df, x='Date', y='Balance', color='Peer ID',
                              title='Node Balances Over Time',
                              labels={'Balance': 'Balance', 'Date': 'Date'},
                              hover_data={'Peer ID': True, 'Balance': True})

        # Plot: Quil Earned Per Minute
        quil_per_minute_fig = px.bar(combined_df, x='Date', y='Quil_Per_Minute', color='Peer ID',
                                     title='Quil Earned Per Minute',
                                     labels={'Quil_Per_Minute': 'Quil Earned/Min'},
                                     hover_data={'Peer ID': True, 'Quil_Per_Minute': True})

        # Plot: Hourly Growth in Quil
        hourly_growth_fig = px.area(hourly_growth_df, x='Hour', y='Growth', color='Peer ID',
                                    title='Hourly Growth in Quil',
                                    labels={'Growth': 'Growth (Quil)', 'Hour': 'Hour'},
                                    hover_data={'Peer ID': True, 'Growth': True})

        # Plot: Earnings per Hour in USD
        earnings_per_hour_fig = px.bar(hourly_growth_df, x='Hour', y='Earnings_USD', color='Peer ID',
                                       title='Earnings in USD per Hour',
                                       labels={'Earnings_USD': 'Earnings (USD)', 'Hour': 'Hour'},
                                       hover_data={'Peer ID': True, 'Earnings_USD': True})

        # Set theme based on night mode
        chart_template = 'plotly_dark' if night_mode == 'on' else 'plotly'

        # Apply the theme to all charts
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

        balance_graph_html = quil_minute_graph_html = hourly_growth_graph_html = ""
        earnings_per_hour_graph_html = ""

    return render_template('index.html',
                           table_data=table_data,
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
