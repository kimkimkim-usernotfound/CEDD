import os
from flask import Flask, render_template, send_from_directory
import time

# Get the absolute path to the directory containing app.py
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(basedir, 'templates'),
    static_folder=os.path.join(basedir, 'static')
)

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
    
    return render_template('index.html', last_update=last_update)

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)
