import requests
import time
import win32gui
import spotify_detector

# --- Configuration ---
SERVER_URL = "https://listeningtogether.onrender.com" # Remember to replace this

# --- NetEase Detector (kept from before) ---
def get_current_netease_song():
    try:
        hwnd = win32gui.FindWindow("OrpheusBrowserHost", None)
        if hwnd == 0: return None
        window_title = win32gui.GetWindowText(hwnd)
        if ' - ' in window_title:
            song, artist = window_title.split(' - ', 1)
            return song.strip(), artist.strip()
        return None
    except Exception:
        return None

def main():
    """
    Main loop for the desktop assistant.
    """
    # --- User Setup at Startup ---
    username = input("Please enter your username for the listening room: ")
    if not username:
        print("Username cannot be empty. Exiting.")
        return

    platform_choice = ''
    while platform_choice not in ['1', '2']:
        platform_choice = input("Which music platform do you want to detect?\n1: NetEase Cloud Music\n2: Spotify\nEnter 1 or 2: ")

    platform_name = ''
    get_song_function = None

    if platform_choice == '1':
        platform_name = 'netease'
        get_song_function = get_current_netease_song
        print("Selected NetEase Cloud Music.")
    else:
        platform_name = 'spotify'
        # Initialize Spotify client, which may require user browser authorization
        if not spotify_detector.initialize_spotify():
            print("Could not initialize Spotify. Please check your credentials and try again.")
            return
        get_song_function = spotify_detector.get_current_spotify_song
        print("Selected Spotify.")

    print(f"Welcome, {username}! Starting song reporting for {platform_name}...")
    print("Press Ctrl+C to stop.")
    
    last_song_title = None

    while True:
        try:
            song_info = get_song_function()
            
            if song_info:
                song, artist = song_info
                current_song_title = f"{song} - {artist}"

                if current_song_title != last_song_title:
                    print(f"New song detected: {current_song_title}")
                    last_song_title = current_song_title
                    
                    try:
                        payload = {
                            "user": username,
                            "song": current_song_title,
                            "platform": platform_name  # Add platform info
                        }
                        response = requests.post(SERVER_URL, json=payload, timeout=5)
                        
                        if response.status_code == 200:
                            print("Successfully sent update to the server.")
                        else:
                            print(f"Failed to send update. Server responded with: {response.status_code}")
                            
                    except requests.exceptions.RequestException as e:
                        print(f"Error connecting to the server: {e}")

            else:
                if last_song_title is not None:
                    print("Playback stopped or music client closed.")
                    last_song_title = None
            
            time.sleep(5)

        except KeyboardInterrupt:
            print("\nStopping the assistant. Goodbye!")
            break
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            time.sleep(10)

if __name__ == '__main__':
    main()
