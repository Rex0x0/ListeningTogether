from flask import Flask, request, jsonify, render_template # Import render_template
from flask_cors import CORS
import time

app = Flask(__name__)
CORS(app)

# In-memory "database"
room_state = {}
INACTIVE_THRESHOLD = 30 

# --- THE FIX IS HERE: Restore the root route ---
@app.route('/')
def index():
    """Serves the HTML page, useful for quick server status checks."""
    # We can return a simple message or the original HTML file.
    # Returning the original HTML is better for future use.
    return render_template('index.html')

def cleanup_inactive_users():
    """Removes users who haven't sent an update recently."""
    global room_state
    current_time = time.time()
    inactive_users = [
        user for user, data in room_state.items() 
        if current_time - data.get("timestamp", 0) > INACTIVE_THRESHOLD
    ]
    for user in inactive_users:
        del room_state[user]

@app.route('/update_state', methods=['POST'])
def update_state():
    """Receives a song update from a desktop client."""
    global room_state
    data = request.get_json()
    if not data or 'user' not in data:
        return jsonify({"status": "error", "message": "Invalid data"}), 400
    
    user = data.get('user')
    
    room_state[user] = {
        "song": data.get("song", ""),
        "platform": data.get("platform", "unknown"),
        "art_url": data.get("art_url"),
        "timestamp": time.time()
    }
    
    return jsonify({"status": "success"})

@app.route('/get_state', methods=['GET'])
def get_state():
    """Returns the current state of the entire room."""
    cleanup_inactive_users()
    return jsonify(room_state)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
