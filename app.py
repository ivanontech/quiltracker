from flask import Flask, request, render_template
import pandas as pd
import plotly.express as px
import os

app = Flask(__name__)

# Path to the directory where CSV files are stored
CSV_DIRECTORY = "/root/quiltracker"

# Helper function to compute Quil Earned Per Minute and Hourly Growth
def compute_metrics(df):
    df['Date'] = pd.to_datetime(df['Date'])
    df['Balance'] = df['Balance'].astype(float)

    # Calculate Quil earned per minute
    df['Time_Diff'] = df.groupby('Peer ID')['Date'].diff().dt.total_seconds() / 60
    df['Quil_Per_Minute'] = df.groupby('Peer ID')['Balance'].diff() / df['Time_Diff']
    df['Quil_Per_Minute'].fillna(0, inplace=True)

    # Calculate cumulative growth per hour
    df['Hour'] = df['Date'].dt.floor('H')
    hourly_growth = df.groupby(['Peer ID', 'Hour'])['Balance'].last().reset_index()
    hourly_growth['Growth'] = hourly_growth.groupby('Peer ID')['Balance'].diff().fillna(0)

    return df, hourly_growth

@app.route('/')
def index():
    data_frames = []

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

        # Compute Quil earned per minute and hourly growth
        combined_df, hourly_growth_df = compute_metrics(combined_df)

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

        # Convert Plotly figures to HTML for rendering
        balance_graph_html = balance_fig.to_html(full_html=False)
        quil_minute_graph_html = quil_per_minute_fig.to_html(full_html=False)
        hourly_growth_graph_html = hourly_growth_fig.to_html(full_html=False)

    else:
        balance_graph_html = ""
        quil_minute_graph_html = ""
        hourly_growth_graph_html = ""

    return render_template('index.html', balance_graph_html=balance_graph_html,
                           quil_minute_graph_html=quil_minute_graph_html,
                           hourly_growth_graph_html=hourly_growth_graph_html)


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
