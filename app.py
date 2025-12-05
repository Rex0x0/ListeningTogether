# IMPORTANT: This must be the very first thing to run
import eventlet
eventlet.monkey_patch()

import json # Import Python's built-in json library
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key!' 
socketio = SocketIO(app, async_mode='eventlet')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/update_song', methods=['POST'])
def update_song():
    # --- ULTIMATE DEBUGGING ---
    # This function will now be extremely verbose to find the issue.
    print("--- DEBUG: /update_song endpoint was hit! ---")
    
    raw_body = request.data
    print(f"1. Raw request body (bytes): {raw_body}")

    if not raw_body:
        print("Error: Request body is empty.")
        return jsonify({"status": "error", "message": "Request body is empty"}), 400

    try:
        # Manually decode the byte string to a UTF-8 string
        body_str = raw_body.decode('utf-8')
        print(f"2. Decoded body (string): {body_str}")
        
        # Manually parse the string into a Python dictionary
        data = json.loads(body_str)
        print(f"3. Parsed JSON data (dict): {data}")

    except Exception as e:
        print(f"Error: Failed to decode or parse JSON. Error: {e}")
        return jsonify({"status": "error", "message": f"JSON parsing failed: {e}"}), 400

    # Now, we can safely access the data
    user = data.get('user')
    song = data.get('song')
    platform = data.get('platform', 'unknown')

    if not user or not song:
        print("Error: 'user' or 'song' field is missing in the parsed JSON.")
        return jsonify({"status": "error", "message": "Missing 'user' or 'song' fields"}), 400
    
    print(f"4. Successfully extracted data: User='{user}', Song='{song}', Platform='{platform}'")
    
    # --- Back to normal operation ---
    socketio.emit('song_update', {'user': user, 'song': song, 'platform': platform})
    print("5. Broadcasted update via WebSocket.")
    
    return jsonify({"status": "success", "message": "Update received"})

@socketio.on('connect')
def handle_connect():
    print('A new client has connected to the WebSocket.')

@socketio.on('disconnect')
def handle_disconnect():
    print('A client has disconnected.')

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
