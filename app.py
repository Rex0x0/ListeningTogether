from flask import Flask, request, jsonify
from flask_cors import CORS
import time

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# In-memory "database"
room_state = {}
INACTIVE_THRESHOLD = 30 

def cleanup_inactive_users():
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
    global room_state
    data = request.get_json()
    if not data or 'user' not in data:
        return jsonify({"status": "error", "message": "Invalid data"}), 400
    
    user = data.get('user')
    
    room_state[user] = {
        "song": data.get("song", ""),
        "platform": data.get("platform", "unknown"),
        "timestamp": time.time()
    }
    
    return jsonify({"status": "success"})

@app.route('/get_state', methods=['GET'])
def get_state():
    cleanup_inactive_users()
    return jsonify(room_state)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
