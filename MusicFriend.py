import tkinter as tk
import threading
import time
import requests
from PIL import Image, ImageTk
import io
import netease_client

# --- Global variables ---
currently_displayed_song = None
album_cover_photo = None # To hold a reference to the PhotoImage

def update_album_art(image_url):
    """Downloads the image and updates the album cover label."""
    global album_cover_photo
    try:
        # Download image data
        response = requests.get(image_url, timeout=5)
        response.raise_for_status() # Raise an exception for bad status codes
        image_data = response.content
        
        # Open image data with Pillow and resize
        pil_image = Image.open(io.BytesIO(image_data))
        pil_image = pil_image.resize((200, 200), Image.LANCZOS)
        
        # Convert to PhotoImage and update the label
        album_cover_photo = ImageTk.PhotoImage(pil_image)
        album_cover_label.config(image=album_cover_photo)
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading image: {e}")
        # Optionally, display a placeholder image on error
        album_cover_label.config(image=placeholder_photo)
    except Exception as e:
        print(f"Error processing image: {e}")
        album_cover_label.config(image=placeholder_photo)


def polling_loop():
    """Periodically checks for the current song and updates the UI."""
    global currently_displayed_song
    
    while True:
        song_info, error_message = netease_client.get_current_netease_song()
        
        if song_info:
            song, artist = song_info
            
            if song != currently_displayed_song:
                print(f"New song detected: {song}")
                currently_displayed_song = song
                
                # Update text immediately to show we're working
                commentary_text.set(f"▶ Now Playing: {song} - {artist}\n\nFetching details...")
                album_cover_label.config(image=placeholder_photo) # Show placeholder while loading

                # Get detailed track info (now returns a dictionary)
                track_details, detail_error = netease_client.get_track_info(song, artist)
                
                if track_details:
                    # Format the commentary string
                    commentary = (
                        f"Song: {track_details['name']}\n"
                        f"Artist(s): {track_details['artist']}\n"
                        f"Album: {track_details['album']}\n"
                        f"Released: {track_details['release_year']}"
                    )
                    commentary_text.set(commentary)
                    
                    # Update album art in a separate thread to not block the UI
                    threading.Thread(target=update_album_art, args=(track_details['cover_url'],), daemon=True).start()
                else:
                    commentary_text.set(detail_error)

        else:
            if currently_displayed_song is not None or "Welcome" in commentary_text.get():
                currently_displayed_song = None
                commentary_text.set(error_message or "Waiting for a song to play...")
                album_cover_label.config(image=placeholder_photo)

        time.sleep(5)

# --- GUI Setup ---
root = tk.Tk()
root.title("MusicFriend")
root.geometry("500x240") # Adjusted size
root.configure(bg="#f0f0f0")

main_frame = tk.Frame(root, padx=10, pady=10, bg="#f0f0f0")
main_frame.pack(fill=tk.BOTH, expand=True)

# --- Placeholder Image ---
placeholder_image = Image.new('RGB', (200, 200), color = '#e0e0e0')
placeholder_photo = ImageTk.PhotoImage(placeholder_image)

# --- Left Frame for Album Cover ---
left_frame = tk.Frame(main_frame, width=200, height=200, bg="#f0f0f0")
left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
left_frame.pack_propagate(False) # Prevents the frame from shrinking

album_cover_label = tk.Label(left_frame, image=placeholder_photo, bg="#e0e0e0")
album_cover_label.pack(fill=tk.BOTH, expand=True)

# --- Right Frame for Text Info ---
right_frame = tk.Frame(main_frame, bg="#f0f0f0")
right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

commentary_text = tk.StringVar()
commentary_label = tk.Label(
    right_frame, 
    textvariable=commentary_text, 
    wraplength=260, # Adjusted for new layout
    justify=tk.LEFT, 
    anchor=tk.NW, 
    font=("Segoe UI", 10),
    bg="#f0f0f0"
)
commentary_label.pack(fill=tk.BOTH, expand=True)
commentary_text.set("Welcome to MusicFriend! Initializing...")

# --- Start Background Thread ---
polling_thread = threading.Thread(target=polling_loop, daemon=True)
polling_thread.start()

netease_client.initialize_netease()

root.mainloop()
