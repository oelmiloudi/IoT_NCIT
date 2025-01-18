import requests
import pymysql
from sqlalchemy import create_engine, text
import pandas as pd
import time
import json
from io import StringIO
from datetime import datetime, timedelta

ZENTRA_API_URL = "https://zentracloud.com/api/v4/get_readings/"
ZENTRA_DEVICE_SN = "z6-26142"
ZENTRA_API_KEY = "4447a79ff801823b5ba3dd151af75755668ce615"
ZENTRA_START_DATE = "2025-01-16 00:00"
ZENTRA_END_DATE = "2025-01-18 00:00"

THINGSPEAK_CHANNEL_ID = '2489769'
THINGSPEAK_API_KEY = '37J7D7JP4SXSU6X2'
THINGSPEAK_API_URL = f'https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL_ID}/feeds.json'
THINGSPEAK_START_DATE = "2025-01-16 00:00:00-06:00"
THINGSPEAK_END_DATE = "2025-01-18 00:00:00-06:00"

DATABASE_CONFIG = {
    'user': 'iot-project-db',
    'password': 'IoTNCIT2024',
    'host': '34.174.9.65',  
    'database': 'IoT_NCIT',
}

def zentra_retrieve_data_for_period(device_sn, period_start, period_end):
    headers = {
        "Authorization": f"Token {ZENTRA_API_KEY}",
        "accept": "application/json"
    }
    
    page_num = 1
    per_page = 2000  
    all_data = []
    rate_limited = False

    while True:
        params = {
            "device_sn": device_sn,
            "start_date": period_start,
            "end_date": period_end,
            "output_format": "df",
            "page_num": page_num,
            "per_page": per_page,
            "sort_by": "desc"
        }

        print(f"Fetching ZENTRA page {page_num} for period {period_start} to {period_end}...")
        response = requests.get(ZENTRA_API_URL, headers=headers, params=params)

        if response.status_code == 429:
            print("ZENTRA rate limit reached. Waiting for 60 seconds before retrying...")
            rate_limited = True
            time.sleep(60)
            continue
        elif response.status_code != 200:
            print(f"Error retrieving ZENTRA data: {response.status_code}")
            break

        try:
            content = response.json()
            if 'data' in content:
                df = pd.read_json(StringIO(content['data']), orient='split')
                if df.empty:
                    print("No more ZENTRA data available for this period.")
                    break
                else:
                    print(f"ZENTRA page {page_num} retrieved with {len(df)} rows for period {period_start} to {period_end}.")
                    all_data.append(df)
                    page_num += 1  # Move to the next page
            else:
                print("Error: 'data' not found in ZENTRA response.")
                break
                
        except Exception as e:
            print(f"Error reading ZENTRA DataFrame from response: {e}")
            break

        if rate_limited:
            rate_limited = False

    if all_data:
        print(f"Concatenating all ZENTRA data for period {period_start} to {period_end}...")
        return pd.concat(all_data, ignore_index=True)
    else:
        print("No ZENTRA data was retrieved for this period.")
        return pd.DataFrame()

def zentra_pivot_and_insert_readings(df):
    if df.empty or 'datetime' not in df.columns:
        print("Error: ZENTRA DataFrame is empty or 'datetime' column is missing.")
        return
    
    df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce', utc=True)  # Convert 'datetime' to UTC and handle invalid values
    if df['datetime'].isnull().any():  
        print(f"Warning: {df['datetime'].isnull().sum()} invalid datetime values were coerced to NaT.")

    # Now perform the 'dt.floor' operation on the 'datetime' column
    df['timestamp'] = df['datetime'].dt.floor('H')

    # create a unique column name for each sensor measurement
    df['sensor_measurement'] = df['sensor_name'] + " - " + df['measurement']

    # pivot the table so each sensor and measurement combination is a column
    df_pivot = df.pivot_table(index='timestamp', columns='sensor_measurement', values='value', aggfunc='mean').reset_index()

    # round all numeric columns in df_pivot to two decimal places
    df_pivot = df_pivot.round(2)

    # rename columns to remove spaces and make them SQL-friendly
    df_pivot.columns = [col.replace(" ", "_") for col in df_pivot.columns]

    # connect to the Google CloudSQL database
    engine = create_engine(
    f"mysql+pymysql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@"
    f"{DATABASE_CONFIG['host']}/{DATABASE_CONFIG['database']}"
)

    try:
        df_pivot.to_sql("SensorReadings", con=engine, if_exists="append", index=False)
        print("ZENTRA data inserted into the SQL database successfully.")
    except Exception as e:
        print(f"Error inserting ZENTRA data into the database: {e}")

def zentra_retrieve_data_in_weekly_segments(device_sn, start_date, end_date):
    # create date ranges for each week
    date_ranges = pd.date_range(start=start_date, end=end_date, freq='7D').tolist()
    
    # add the end_date as the final element if it's not already in the list
    if pd.to_datetime(end_date) not in date_ranges:
        date_ranges.append(pd.to_datetime(end_date))
    
    for i in range(len(date_ranges) - 1):
        period_start = date_ranges[i].strftime('%Y-%m-%d %H:%M:%S')
        period_end = date_ranges[i + 1].strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"\nRetrieving ZENTRA data for period: {period_start} to {period_end}...")
        readings_df = zentra_retrieve_data_for_period(device_sn, period_start, period_end)
        
        if not readings_df.empty:
            zentra_pivot_and_insert_readings(readings_df)
        else:
            print(f"No ZENTRA data retrieved for period: {period_start} to {period_end}.")

def thingspeak_find_nearest_hour_readings(df):
    # create perfect hours within the data range
    min_time = df['timestamp'].min().floor('h')
    max_time = df['timestamp'].max().floor('h')
    timezone = df['timestamp'].dt.tz  # get the timezone from the data
    
    # create date range with the same timezone
    perfect_hours = pd.date_range(
        start=min_time,
        end=max_time,
        freq='H',
        tz=timezone  # explicitly set the timezone
    )
    
    nearest_readings = []
    
    for perfect_hour in perfect_hours:
        # calculate time difference between perfect hour and all readings
        time_diff = abs(df['timestamp'] - perfect_hour)
        
        # find the index of the closest reading
        closest_idx = time_diff.idxmin()
        
        # get the closest reading's data
        closest_reading = df.loc[closest_idx].copy()
        
        # store the original time for logging
        original_time = closest_reading['timestamp']
        
        # set the timestamp to the perfect hour while preserving timezone
        closest_reading['timestamp'] = perfect_hour
        
        nearest_readings.append(closest_reading)
        
        print(f"Perfect hour: {perfect_hour}, Used reading from: {original_time}")
    
    # convert list of readings to DataFrame
    result_df = pd.DataFrame(nearest_readings)
    return result_df

def thingspeak_retrieve_data_for_period(start_date, end_date):
    params = {
        'api_key': THINGSPEAK_API_KEY,
        'start': start_date,
        'end': end_date,
        'results': 8000  # thingSpeak maximum results per request
    }
    
    try:
        print(f"Fetching ThingSpeak data for period {start_date} to {end_date}...")
        response = requests.get(THINGSPEAK_API_URL, params=params)
        
        if response.status_code != 200:
            print(f"Error retrieving ThingSpeak data: {response.status_code}")
            return pd.DataFrame()
            
        content = response.json()
        
        if 'feeds' in content and content['feeds']:
            # convert to DataFrame
            df = pd.DataFrame(content['feeds'])
            
            # convert timestamp and set to Central Time
            df['timestamp'] = pd.to_datetime(df['created_at']).dt.tz_convert('America/Chicago')
            df = df.drop('created_at', axis=1)
            
            # rename field columns and convert to float
            df['Pitch'] = pd.to_numeric(df['field1'], errors='coerce')
            df['Roll'] = pd.to_numeric(df['field2'], errors='coerce')
            
            # drop original field columns and entry_id
            df = df.drop(['field1', 'field2', 'entry_id'], axis=1)
            
            # find nearest readings to perfect hours (timezone will be preserved)
            df = thingspeak_find_nearest_hour_readings(df)
            
            # round values to 2 decimal places
            df = df.round(2)
            
            print(f"\nRetrieved {len(df)} hourly ThingSpeak records for period {start_date} to {end_date}")
            return df
        else:
            print("No ThingSpeak data found in the response.")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"Error processing ThingSpeak data: {e}")
        return pd.DataFrame()

def thingspeak_create_database_and_table():
    try:
        # Google CloudSQL engine
        engine = create_engine(
    f"mysql+pymysql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@"
    f"{DATABASE_CONFIG['host']}/{DATABASE_CONFIG['database']}"
)

        
        # create table if it doesn't exist
        create_table_query = """
        CREATE TABLE IF NOT EXISTS ThingSpeak (
            id INT AUTO_INCREMENT PRIMARY KEY,
            timestamp DATETIME,
            Pitch FLOAT,
            Roll FLOAT,
            UNIQUE KEY unique_timestamp (timestamp)
        )
        """
        
        with engine.connect() as conn:
            conn.execute(text(create_table_query))
            print("ThingSpeak table created successfully or already exists.")
            
        return engine
    except Exception as e:
        print(f"Error creating ThingSpeak database or table: {e}")
        return None

def thingspeak_insert_readings(df, engine):
    if df.empty:
        print("No ThingSpeak data to insert.")
        return
        
    try:
        # insert data into the database, ignore duplicates
        df.to_sql('ThingSpeak', con=engine, if_exists='append', index=False, 
                  method='multi', chunksize=1000)
        print(f"Successfully inserted {len(df)} hourly ThingSpeak readings into the database.")
    except Exception as e:
        print(f"Error inserting ThingSpeak data into database: {e}")

def thingspeak_retrieve_data_in_weekly_segments(start_date, end_date):
    # create database and table
    engine = thingspeak_create_database_and_table()
    if not engine:
        return
        
    # create date ranges for each week
    date_ranges = pd.date_range(start=start_date, end=end_date, freq='7D').tolist()
    
    # add the end_date as the final element if it's not already in the list
    if pd.to_datetime(end_date) not in date_ranges:
        date_ranges.append(pd.to_datetime(end_date))
    
    for i in range(len(date_ranges) - 1):
        period_start = date_ranges[i].strftime('%Y-%m-%d %H:%M:%S')
        period_end = date_ranges[i + 1].strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"\nRetrieving ThingSpeak data for period: {period_start} to {period_end}...")
        readings_df = thingspeak_retrieve_data_for_period(period_start, period_end)
        
        if not readings_df.empty:
            thingspeak_insert_readings(readings_df, engine)
        else:
            print(f"No ThingSpeak data retrieved for period: {period_start} to {period_end}.")
        
        # add a small delay to avoid hitting rate limits
        time.sleep(1)

def get_zentracloud_data_from_db(start_date, end_date):
    engine = create_engine(
        f"mysql+pymysql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@"
        f"{DATABASE_CONFIG['host']}/{DATABASE_CONFIG['database']}"
    )

    with engine.connect() as conn:
        query = text("""
            SELECT *
            FROM SensorReadings
            WHERE timestamp >= :start_date AND timestamp <= :end_date
            ORDER BY timestamp ASC
        """)
        df = pd.read_sql(query, conn, params={"start_date": start_date, "end_date": end_date})

    # Handle null timestamps
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df.dropna(subset=['timestamp'], inplace=True)

    return df


def get_thingspeak_data_from_db(start_date, end_date):
    """
    Retrieve data from the 'thingspeak_data' table within a given date range.
    If start_date or end_date is empty, retrieve all rows.
    """
    engine = create_engine(
    f"mysql+pymysql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@"
    f"{DATABASE_CONFIG['host']}/{DATABASE_CONFIG['database']}"
)

    with engine.connect() as conn:
        if start_date and end_date:
            query = text("""
                SELECT *
                FROM ThingSpeak
                WHERE timestamp >= :start_date
                  AND timestamp <= :end_date
                ORDER BY timestamp ASC
            """)
            df = pd.read_sql(query, conn, params={"start_date": start_date, "end_date": end_date})
        else:
            # If either start_date or end_date is empty, return all rows
            query = text("SELECT * FROM ThingSpeak ORDER BY timestamp ASC")
            df = pd.read_sql(query, conn)

    # Handle null timestamps
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df.dropna(subset=['timestamp'], inplace=True)

    return df

if __name__ == "__main__":
    # First retrieve and insert ZENTRA data
    zentra_retrieve_data_in_weekly_segments(ZENTRA_DEVICE_SN, ZENTRA_START_DATE, ZENTRA_END_DATE)
    
    # Then retrieve and insert ThingSpeak data
    thingspeak_retrieve_data_in_weekly_segments(THINGSPEAK_START_DATE, THINGSPEAK_END_DATE)
    pass
