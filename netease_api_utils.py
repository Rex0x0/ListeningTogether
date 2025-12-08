from PyNeteaseCloudMusic import API

# Initialize the API
# We don't need to log in for searching songs
api = API()

def get_netease_album_art_url(song_name, artist_name):
    """
    Searches for a song on NetEase Cloud Music and returns the album art URL.
    
    Args:
        song_name (str): The name of the song.
        artist_name (str): The name of the artist.
        
    Returns:
        str: The URL of the album art, or None if not found.
    """
    # Construct a search query
    query = f"{song_name} {artist_name}"
    print(f"Netease API: Searching for '{query}'...")
    
    try:
        # Type 1 is for searching songs
        result = api.search(query, 1)
        
        if result and result.get('result', {}).get('songs'):
            # Get the first song from the search results
            first_song = result['result']['songs'][0]
            
            # Extract the album art URL
            # The 'al' key stands for album, and 'picUrl' is the cover image URL.
            if 'al' in first_song and 'picUrl' in first_song['al']:
                art_url = first_song['al']['picUrl']
                print(f"Netease API: Found album art URL: {art_url}")
                return art_url
            else:
                print("Netease API: Song found, but no album art URL available.")
                return None
        else:
            print("Netease API: No songs found for the query.")
            return None
            
    except Exception as e:
        print(f"An error occurred while searching NetEase API: {e}")
        return None

if __name__ == '__main__':
    # Example usage for testing
    # Replace with a known song and artist
    test_song = "七里香"
    test_artist = "周杰伦"
    url = get_netease_album_art_url(test_song, test_artist)
    
    if url:
        print(f"\nSuccessfully found URL for '{test_song}': {url}")
    else:
        print(f"\nCould not find album art for '{test_song}'.")
