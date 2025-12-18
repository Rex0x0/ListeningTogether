from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import time

app = Flask(__name__)
CORS(app)
# Re-initialize SocketIO, using eventlet for production
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# --- In-memory "database" for song state (unchanged) ---
room_state = {}
INACTIVE_THRESHOLD = 30 

# --- HTTP Routes for Song Polling (unchanged) ---
@app.route('/')
def index():
    return render_template('index.html')

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
        "art_url": data.get("art_url"),
        "timestamp": time.time()
    }
    return jsonify({"status": "success"})

@app.route('/get_state', methods=['GET'])
def get_state():
    cleanup_inactive_users()
    return jsonify(room_state)

# --- NEW: WebSocket Handlers for Live Chat ---
@socketio.on('connect')
def handle_connect():
    print('Chat client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Chat client disconnected')

@socketio.on('send_message')
def handle_send_message(data):
    """
    Receives a message from a client and broadcasts it to all clients.
    'data' is expected to be a dictionary, e.g., {'user': 'rex', 'message': 'Hello!'}
    """
    print(f"Received message from {data.get('user')}: {data.get('message')}")
    # Broadcast the message to all connected clients, including the sender.
    emit('new_message', data, broadcast=True)

if __name__ == '__main__':
    # Use socketio.run() for local testing with WebSocket support
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
