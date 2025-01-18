from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import pytz

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

        df = get_zentracloud_data_from_db(start, end)
        if df.empty:
            return jsonify({'error': 'No data found for the specified range'}), 404

        data = df.to_dict(orient='list')
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_thingspeak_data')
def get_thingspeak_data():
    try:
        start = request.args.get('start', '') 
        end = request.args.get('end', '')     

        df = get_thingspeak_data_from_db(start, end)
        if df.empty:
            return jsonify({'error': 'No data found for the specified range'}), 404

        if 'id' in df.columns:
            df = df.drop(['id'], axis=1)

        data = df.to_dict(orient='list')
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
