import os
from flask import Flask, render_template, send_from_directory
from flask_apscheduler import APScheduler
import time
import pandas as pd
import subprocess

# Get the absolute path to the directory containing app.py
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(basedir, 'templates'),
    static_folder=os.path.join(basedir, 'static')
)

# Configuration for APScheduler
class Config:
    SCHEDULER_API_ENABLED = True

app.config.from_object(Config())
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

def update_data():
    """Function to run the scrapers"""
    print("Updating data (Weekly Job)...")
    python_path = r'C:\Users\yulin\AppData\Local\Programs\Python\Python312\python.exe'
    
    # Run scrape_contracts.py
    subprocess.run([python_path, 'scrape_contracts.py'])
    
    # Run scrape_forecast.py
    subprocess.run([python_path, 'scrape_forecast.py'])
    print("Data update complete.")

# Schedule the update every Monday at 00:00
@scheduler.task('cron', id='weekly_update', day_of_week='mon', hour=0, minute=0)
def weekly_update_job():
    update_data()

# Inject the time module into templates to avoid caching issues with the image
@app.context_processor
def inject_time():
    return dict(time=time.time)

@app.route('/')
def index():
    last_update = "Never"
    if os.path.exists('static/last_update.txt'):
        with open('static/last_update.txt', 'r') as f:
            last_update = f.read()
            
    last_forecast_update = "Never"
    if os.path.exists('static/last_forecast_update.txt'):
        with open('static/last_forecast_update.txt', 'r') as f:
            last_forecast_update = f.read()
    
    # Load forecast data
    forecasts = []
    if os.path.exists('static/tender_forecast.csv'):
        df_forecast = pd.read_csv('static/tender_forecast.csv')
        forecasts = df_forecast.to_dict('records')
        
    return render_template(
        'index.html', 
        last_update=last_update, 
        last_forecast_update=last_forecast_update,
        forecasts=forecasts
    )

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

if __name__ == "__main__":
    app.run(debug=True, port=8000)
