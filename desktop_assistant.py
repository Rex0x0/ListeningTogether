import requests
import time
import win32gui

# --- Configuration ---
# This should be the address of your Flask server.
# If you run both on the same machine, this is correct.
SERVER_URL = "https://listeningtogether.onrender.com"

def get_current_netease_song():
    """
    Finds the NetEase Cloud Music window and extracts the current song.
    Returns (song, artist) tuple or None if not found.
    """
    try:
        hwnd = win32gui.FindWindow("OrpheusBrowserHost", None)
        if hwnd == 0:
            return None
        
        window_title = win32gui.GetWindowText(hwnd)
        
        if ' - ' in window_title:
            song, artist = window_title.split(' - ', 1)
            return song.strip(), artist.strip()
        else:
            return None
            
    except Exception:
        return None

def main():
    """
    Main loop for the desktop assistant.
    """
    username = input("Please enter your username for the listening room: ")
    if not username:
        print("Username cannot be empty. Exiting.")
        return

    print(f"Welcome, {username}! Starting song reporting...")
    print("Press Ctrl+C to stop.")
    
    last_song_title = None

    while True:
        try:
            song_info = get_current_netease_song()
            
            if song_info:
                song, artist = song_info
                current_song_title = f"{song} - {artist}"

                # --- Check if the song has changed ---
                if current_song_title != last_song_title:
                    print(f"New song detected: {current_song_title}")
                    last_song_title = current_song_title
                    
                    # --- Send the update to the server ---
                    try:
                        payload = {
                            "user": username,
                            "song": current_song_title
                        }
                        response = requests.post(SERVER_URL, json=payload, timeout=5)
                        
                        if response.status_code == 200:
                            print("Successfully sent update to the server.")
                        else:
                            print(f"Failed to send update. Server responded with: {response.status_code}")
                            
                    except requests.exceptions.RequestException as e:
                        print(f"Error connecting to the server: {e}")

            else:
                # If no song is detected, and the last song was not None
                if last_song_title is not None:
                    print("Playback stopped or NetEase Music closed.")
                    last_song_title = None
            
            # Wait for a few seconds before checking again
            time.sleep(5)

        except KeyboardInterrupt:
            print("\nStopping the assistant. Goodbye!")
            break
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            time.sleep(10) # Wait a bit longer on error

if __name__ == '__main__':
    main()
