# IMPORTANT: This must be the very first thing to run
import eventlet
eventlet.monkey_patch()

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
    # --- START OF DEBUGGING BLOCK ---
    print("--- DEBUG: INCOMING REQUEST ---")
    print(f"Headers: {request.headers}")
    print(f"Content-Type: {request.content_type}")
    print(f"Raw Body: {request.data}")
    print("-----------------------------")
    # --- END OF DEBUGGING BLOCK ---

    data = request.get_json()
    if not data or 'user' not in data or 'song' not in data:
        # This is the error you are likely hitting.
        # The prints above will tell us why get_json() is failing.
        return jsonify({"status": "error", "message": "Could not parse JSON or missing fields"}), 400
        
    user = data.get('user')
    song = data.get('song')
    platform = data.get('platform', 'unknown') 
    
    print(f"Received update via HTTP: User '{user}' on '{platform}' is listening to '{song}'")
    
    socketio.emit('song_update', {'user': user, 'song': song, 'platform': platform})
    
    print(f"Broadcasted via WebSocket: '{user}' on '{platform}' -> '{song}'")
    
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
