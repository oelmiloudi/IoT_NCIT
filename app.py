from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import pytz
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
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    df = get_zentracloud_data_from_db(start, end)
    
    # Convert the entire DataFrame to a dictionary of lists
    # Keys are column names (as in the database), values are lists of values
    data = df.to_dict(orient='list')
    return jsonify(data)

@app.route('/get_thingspeak_data')
def get_thingspeak_data():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    df = get_thingspeak_data_from_db(start, end)
    data = df.to_dict(orient='list')
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
