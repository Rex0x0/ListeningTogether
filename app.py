from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO

# Initialize the Flask app and SocketIO
app = Flask(__name__)
# A secret key is required for sessions, which SocketIO uses.
app.config['SECRET_KEY'] = 'a_very_secret_key!' 
socketio = SocketIO(app, async_mode='eventlet')

# --- HTTP Routes ---

@app.route('/')
def index():
    """
    Serves the main HTML page for the listening room.
    """
    # Flask will look for this file in a 'templates' folder.
    return render_template('index.html')

@app.route('/update_song', methods=['POST'])
def update_song():
    """
    API endpoint to receive song updates from the desktop assistant.
    """
    data = request.get_json()
    if not data or 'user' not in data or 'song' not in data:
        return jsonify({"status": "error", "message": "Invalid data"}), 400
        
    user = data.get('user')
    song = data.get('song')
    
    print(f"Received update via HTTP: User '{user}' is listening to '{song}'")
    
    # --- WebSocket Broadcast ---
    # This is the new part. We emit a 'song_update' event to all connected clients.
    socketio.emit('song_update', {'user': user, 'song': song})
    
    print(f"Broadcasted via WebSocket: '{user}' -> '{song}'")
    
    return jsonify({"status": "success"})

# --- WebSocket Event Handlers ---

@socketio.on('connect')
def handle_connect():
    """
    This function is called when a new user opens the webpage.
    """
    print('A new client has connected to the WebSocket.')

@socketio.on('disconnect')
def handle_disconnect():
    """
    This function is called when a user closes the webpage.
    """
    print('A client has disconnected.')


if __name__ == '__main__':
    # Use socketio.run() to start the server, which supports both Flask routes and WebSockets.
    # We use eventlet as the server, which was installed.
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
