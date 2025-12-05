# IMPORTANT: This must be the very first thing to run
import eventlet
eventlet.monkey_patch()

import json
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key!' 

# THE FIX: Let SocketIO auto-detect the async mode (eventlet) from Gunicorn
socketio = SocketIO(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/update_song', methods=['POST'])
def update_song():
    # This endpoint is now primarily for the web-based JS bridge version,
    # but we keep it for compatibility and testing.
    # The pure desktop app will use WebSocket events directly.
    print("--- DEBUG: /update_song endpoint (HTTP) was hit! ---")
    
    raw_body = request.data
    print(f"1. Raw request body (bytes): {raw_body}")

    if not raw_body:
        return jsonify({"status": "error", "message": "Request body is empty"}), 400

    try:
        body_str = raw_body.decode('utf-8')
        data = json.loads(body_str)
    except Exception as e:
        return jsonify({"status": "error", "message": f"JSON parsing failed: {e}"}), 400

    user = data.get('user')
    song = data.get('song')
    platform = data.get('platform', 'unknown')

    if not user or not song:
        return jsonify({"status": "error", "message": "Missing 'user' or 'song' fields"}), 400
    
    print(f"4. Successfully extracted data: User='{user}', Song='{song}', Platform='{platform}'")
    
    # Broadcast the update
    socketio.emit('song_update', {'user': user, 'song': song, 'platform': platform})
    print("5. Broadcasted update via WebSocket.")
    
    return jsonify({"status": "success", "message": "Update received"})

# --- WebSocket Event Handlers ---

@socketio.on('connect')
def handle_connect():
    """This is called when a client (browser or desktop app) connects."""
    print('A new client has connected to the WebSocket.')

@socketio.on('disconnect')
def handle_disconnect():
    print('A client has disconnected.')

@socketio.on('song_update')
def handle_song_update_event(data):
    """
    This handles the 'song_update' event sent directly from the pure desktop app.
    It then broadcasts this update to all other clients.
    """
    print(f"Received 'song_update' event via WebSocket: {data}")
    # The 'broadcast=True' is crucial here! It sends the message to everyone *except* the sender.
    # To include the sender, you would add `include_self=True`.
    # For our use case, we want everyone to get the update.
    socketio.emit('song_update', data, broadcast=True)
    print("Re-broadcasted event to all clients.")


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    # When running locally, we still need to specify the async_mode
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
