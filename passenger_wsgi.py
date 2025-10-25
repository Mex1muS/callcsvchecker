import sys
import os

# 1. Update the Python Path (Essential)
# Add the current directory to the system path so Python can find app.py
sys.path.insert(0, os.path.dirname(__file__))

# 2. Import the Flask App instance from your app.py file
# Assuming your Flask app instance is named 'app' (e.g., app = Flask(__name__))
from app import app as application

# If you need to set the debug mode off (recommended for live site)
application.debug = False

# The server will look for the 'application' variable to run your app
# (No need for if __name__ == '__main__':)