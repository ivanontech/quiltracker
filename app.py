from flask import Flask, request, render_template
import pandas as pd
import plotly.express as px
import os
import requests

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

# Helper function to compute Quil Earned Per Minute and Hourly Growth
def compute_metrics(df, wquil_price):
    df['Date'] = pd.to_datetime(df['Date'])
    df['Balance'] = df['Balance'].astype(float)

    # Calculate Quil earned per minute
    df['Time_Diff'] = df.groupby('Peer ID')['Date'].diff().dt.total_seconds() / 60
    df['Quil_Per_Minute'] = df.groupby('Peer ID')['Balance'].diff() / df['Time_Diff']
    df['Quil_Per_Minute'] = df['Quil_Per_Minute'].fillna(0)

    # Calculate Quil per hour (60 * Quil per minute)
    df['Quil_Per_Hour'] = df['Quil_Per_Minute'] * 60

    # Calculate Quil per day (24 * Quil per hour)
    df['Quil_Per_Day'] = df['Quil_Per_Hour'] * 24

    # Calculate cumulative growth per hour
    df['Hour'] = df['Date'].dt.floor('h')
    hourly_growth = df.groupby(['Peer ID', 'Hour'])['Balance'].last().reset_index()
    hourly_growth['Growth'] = hourly_growth.groupby('Peer ID')['Balance'].diff().fillna(0)

    # Calculate earnings in USD
    hourly_growth['Earnings_USD'] = hourly_growth['Growth'] * wquil_price
    df['Earnings_Per_Minute'] = df['Quil_Per_Minute'] * wquil_price
    df['Earnings_Per_Hour'] = df['Quil_Per_Hour'] * wquil_price
    df['Earnings_Per_Day'] = df['Quil_Per_Day'] * wquil_price

    return df, hourly_growth

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

        # Calculate the total balance across all Peer IDs
        total_quil_balance = round(latest_balances['Balance'].sum(), 4)

        # Calculate Quil per minute and per hour for each Peer ID
        quil_per_minute = combined_df.groupby('Peer ID')['Quil_Per_Minute'].mean()
        quil_per_hour = combined_df.groupby('Peer ID')['Quil_Per_Hour'].mean()
        quil_per_day = combined_df.groupby('Peer ID')['Quil_Per_Day'].mean()
        dollar_per_hour = combined_df.groupby('Peer ID')['Earnings_Per_Hour'].mean()
        dollar_per_day = combined_df.groupby('Peer ID')['Earnings_Per_Day'].mean()

        latest_balances['Quil Per Minute'] = quil_per_minute.values
        latest_balances['Quil Per Hour'] = quil_per_hour.values
        latest_balances['Quil Per Day'] = quil_per_day.values
        latest_balances['$ Per Hour'] = dollar_per_hour.values
        latest_balances['$ Per Day'] = dollar_per_day.values

        # Sum for the totals row
        total_quil_per_minute = latest_balances['Quil Per Minute'].sum()
        total_quil_per_hour = latest_balances['Quil Per Hour'].sum()
        total_dollar_per_hour = latest_balances['$ Per Hour'].sum()
        total_quil_per_day = latest_balances['Quil Per Day'].sum()
        total_dollar_per_day = latest_balances['$ Per Day'].sum()

        # Data for the table (with Quil Per Hour and Quil Per Minute)
        table_data = latest_balances[['Peer ID', 'Balance', 'Quil Per Minute', 'Quil Per Hour', '$ Per Hour', 'Quil Per Day', '$ Per Day']]

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

        # Plot: Earnings per Minute in USD
        earnings_per_minute_fig = px.line(combined_df, x='Date', y='Earnings_Per_Minute', color='Peer ID',
                                          title='Earnings in USD per Minute',
                                          labels={'Earnings_Per_Minute': 'Earnings (USD/Min)', 'Date': 'Date'},
                                          hover_data={'Peer ID': True, 'Earnings_Per_Minute': True})

        # Set theme based on night mode
        chart_template = 'plotly_dark' if night_mode == 'on' else 'plotly'

        # Apply the theme to all charts
        balance_fig.update_layout(template=chart_template)
        quil_per_minute_fig.update_layout(template=chart_template)
        hourly_growth_fig.update_layout(template=chart_template)
        earnings_per_hour_fig.update_layout(template=chart_template)
        earnings_per_minute_fig.update_layout(template=chart_template)

        # Convert Plotly figures to HTML for rendering
        balance_graph_html = balance_fig.to_html(full_html=False)
        quil_minute_graph_html = quil_per_minute_fig.to_html(full_html=False)
        hourly_growth_graph_html = hourly_growth_fig.to_html(full_html=False)
        earnings_per_hour_graph_html = earnings_per_hour_fig.to_html(full_html=False)
        earnings_per_minute_graph_html = earnings_per_minute_fig.to_html(full_html=False)

    else:
        # In case no data is found, render empty or zero values
        table_data = []
        total_quil_balance = total_quil_per_minute = total_quil_per_hour = 0
        total_dollar_per_hour = total_quil_per_day = total_dollar_per_day = 0

        balance_graph_html = quil_minute_graph_html = hourly_growth_graph_html = ""
        earnings_per_hour_graph_html = earnings_per_minute_graph_html = ""

    return render_template('index.html',
                           table_data=table_data,
                           total_balance=total_quil_balance,
                           total_quil_per_minute=total_quil_per_minute,
                           total_quil_per_hour=total_quil_per_hour,
                           total_dollar_per_hour=total_dollar_per_hour,
                           total_quil_per_day=total_quil_per_day,
                           total_dollar_per_day=total_dollar_per_day,
                           balance_graph_html=balance_graph_html,
                           quil_minute_graph_html=quil_minute_graph_html,
                           hourly_growth_graph_html=hourly_growth_graph_html,
                           earnings_per_hour_graph_html=earnings_per_hour_graph_html,
                           earnings_per_minute_graph_html=earnings_per_minute_graph_html,
                           wquil_price=wquil_price,
                           night_mode=night_mode)

# Route to handle balance data from servers
@app.route('/update_balance', methods=['POST'])
def update_balance():
    try:
        # Log the raw request data for debugging
        data = request.get_json()
        print(f"Received data: {data}")

        # Check if data is valid
        if not data:
            return 'No data received', 400

        # Prepare data to append to a CSV file
        peer_id = data.get('peer_id')
        balance = data.get('balance')
        timestamp = data.get('timestamp')

        if not peer_id or not balance or not timestamp:
            return 'Missing required fields', 400

        log_file = os.path.join(CSV_DIRECTORY, f'node_balance_{peer_id}.csv')

        # Append the data to the corresponding CSV file
        if not os.path.exists(log_file):
            with open(log_file, 'w') as f:
                f.write('Date,Peer ID,Balance\n')

        with open(log_file, 'a') as f:
            f.write(f'{timestamp},{peer_id},{balance}\n')

        print(f"Logged data for Peer ID {peer_id}: Balance {balance} at {timestamp}")
        return 'Balance recorded', 200

    except Exception as e:
        print(f"Error: {e}")
        return 'Internal Server Error', 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
