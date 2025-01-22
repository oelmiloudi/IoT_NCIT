from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import pytz
from sqlalchemy import create_engine, text
import os

from flask_talisman import Talisman

app = Flask(__name__)
Talisman(app)  # Enforces HTTPS

from data_retrieval import (
    get_zentracloud_data_from_db,
    get_thingspeak_data_from_db
)

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('UI.html')

@app.route('/get_zentracloud_data')
def get_zentracloud_data():
    try:
        start = request.args.get('start', '')
        end = request.args.get('end', '')

        # Validate date parameters
        if not start or not end:
            app.logger.warning("Missing or empty start_date and/or end_date in request")
            return jsonify({'error': 'Missing start_date or end_date'}), 400

        # Fetch data from the database
        app.logger.info(f"Fetching ZentraCloud data from {start} to {end}")
        df = get_zentracloud_data_from_db(start, end)

        if df.empty:
            app.logger.warning(f"No data found for ZentraCloud between {start} and {end}")
            return jsonify({'error': 'No data found for the specified range'}), 404

        data = df.to_dict(orient='list')
        app.logger.info(f"Returning ZentraCloud data with {len(df)} records")
        return jsonify(data)
    except Exception as e:
        app.logger.error(f"Error in /get_zentracloud_data: {str(e)}")
        return jsonify({'error': str(e)}), 500



@app.route('/get_thingspeak_data')
def get_thingspeak_data():
    try:
        start = request.args.get('start', '')
        end = request.args.get('end', '')
        app.logger.info(f"Received request to fetch ThingSpeak data from {start} to {end}")

        df = get_thingspeak_data_from_db(start, end)
        if df.empty:
            app.logger.warning(f"No data found for ThingSpeak between {start} and {end}")
            return jsonify({'error': 'No data found for the specified range'}), 404

        if 'id' in df.columns:
            df = df.drop(['id'], axis=1)

        data = df.to_dict(orient='list')
        app.logger.info(f"Returning ThingSpeak data with {len(df)} records")
        return jsonify(data)
    except Exception as e:
        app.logger.error(f"Error in /get_thingspeak_data: {str(e)}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
