import requests
import pandas as pd
import time
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from io import StringIO
import os

# constants
ZENTRA_API_URL = "https://zentracloud.com/api/v4/get_readings/"
ZENTRA_API_KEY = "4447a79ff801823b5ba3dd151af75755668ce615"
ZENTRA_DEVICE_SN = "z6-26142"

THINGSPEAK_CHANNEL_ID = '2489769'
THINGSPEAK_API_KEY = '37J7D7JP4SXSU6X2'
THINGSPEAK_API_URL = f'https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL_ID}/feeds.json'

DB_URL = "mysql+pymysql://root:@localhost:3307/IoT_NCIT"
engine = create_engine(DB_URL)


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

        response = requests.get(ZENTRA_API_URL, headers=headers, params=params)

        if response.status_code == 429:
            rate_limited = True
            time.sleep(60)
            continue
        elif response.status_code != 200:
            break

        content = response.json()
        if 'data' in content:
            df = pd.read_json(StringIO(content['data']), orient='split')
            if df.empty:
                break
            all_data.append(df)
            page_num += 1
        else:
            break

        if rate_limited:
            rate_limited = False

    if all_data:
        return pd.concat(all_data, ignore_index=True)
    else:
        return pd.DataFrame()

def zentra_pivot_and_insert_readings(df):
    if df.empty or 'datetime' not in df.columns:
        return
    
    df['timestamp'] = pd.to_datetime(df['datetime'], utc=True, errors='coerce').dt.floor('H')
    df['sensor_measurement'] = df['sensor_name'] + " - " + df['measurement']
    df_pivot = df.pivot_table(index='timestamp', columns='sensor_measurement', values='value', aggfunc='mean').reset_index()
    df_pivot = df_pivot.round(2)
    df_pivot.columns = [col.replace(" ", "_") for col in df_pivot.columns]

    engine = create_engine(DB_URL)
    df_pivot.to_sql("readings", con=engine, if_exists="append", index=False)

def zentra_retrieve_and_store_data(start_date, end_date):
    # If you prefer weekly segments or direct retrieval:
    df = zentra_retrieve_data_for_period(ZENTRA_DEVICE_SN, start_date, end_date)
    if not df.empty:
        zentra_pivot_and_insert_readings(df)

def thingspeak_create_database_and_table():
    engine = create_engine(DB_URL)
    create_table_query = """
    CREATE TABLE IF NOT EXISTS thingspeak_data (
        id INT AUTO_INCREMENT PRIMARY KEY,
        timestamp DATETIME,
        Pitch FLOAT,
        Roll FLOAT,
        UNIQUE KEY unique_timestamp (timestamp)
    )
    """
    with engine.connect() as conn:
        conn.execute(text(create_table_query))
    return engine

def thingspeak_find_nearest_hour_readings(df):
    min_time = df['timestamp'].min().floor('h')
    max_time = df['timestamp'].max().floor('h')
    timezone = df['timestamp'].dt.tz
    
    perfect_hours = pd.date_range(
        start=min_time,
        end=max_time,
        freq='H',
        tz=timezone
    )

    nearest_readings = []
    for perfect_hour in perfect_hours:
        time_diff = abs(df['timestamp'] - perfect_hour)
        closest_idx = time_diff.idxmin()
        closest_reading = df.loc[closest_idx].copy()
        closest_reading['timestamp'] = perfect_hour
        nearest_readings.append(closest_reading)

    return pd.DataFrame(nearest_readings)

def thingspeak_retrieve_data_for_period(start_date, end_date):
    params = {
        'api_key': THINGSPEAK_API_KEY,
        'start': start_date,
        'end': end_date,
        'results': 8000
    }

    response = requests.get(THINGSPEAK_API_URL, params=params)
    if response.status_code != 200:
        return pd.DataFrame()

    content = response.json()
    if 'feeds' not in content or not content['feeds']:
        return pd.DataFrame()

    df = pd.DataFrame(content['feeds'])
    # Assume the data is in UTC or convert accordingly
    df['timestamp'] = pd.to_datetime(df['created_at']).dt.tz_localize('UTC').dt.tz_convert('America/Chicago')
    df = df.drop('created_at', axis=1)
    df['Pitch'] = pd.to_numeric(df['field1'], errors='coerce')
    df['Roll'] = pd.to_numeric(df['field2'], errors='coerce')
    df = df.drop(['field1', 'field2', 'entry_id'], axis=1)
    df = thingspeak_find_nearest_hour_readings(df)
    df = df.round(2)
    return df

def thingspeak_insert_readings(df, engine):
    if df.empty:
        return
    df.to_sql('thingspeak_data', con=engine, if_exists='append', index=False, method='multi', chunksize=1000)

def thingspeak_retrieve_and_store_data(start_date, end_date):
    engine = thingspeak_create_database_and_table()
    df = thingspeak_retrieve_data_for_period(start_date, end_date)
    if not df.empty:
        thingspeak_insert_readings(df, engine)

def get_zentracloud_data_from_db(start_date='', end_date=''):
    engine = create_engine(DB_URL)
    # Get all columns from the 'readings' table
    query = "SELECT * FROM readings"
    filters = []

    if start_date:
        filters.append(f"timestamp >= '{start_date}'")
    if end_date:
        filters.append(f"timestamp <= '{end_date}'")

    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY timestamp ASC"

    df = pd.read_sql(query, engine)
    return df

def get_thingspeak_data_from_db(start_date='', end_date=''):
    engine = create_engine(DB_URL)
    query = "SELECT timestamp, Pitch, Roll FROM thingspeak_data"
    filters = []
    if start_date:
        filters.append(f"timestamp >= '{start_date}'")
    if end_date:
        filters.append(f"timestamp <= '{end_date}'")

    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY timestamp ASC"
    df = pd.read_sql(query, engine)
    return df
