import os
import requests
from pathlib import Path

def download_icon(url, save_path):
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(response.content)
        print(f"Downloaded {save_path}")
    except Exception as e:
        print(f"Failed to download {url}: {e}")

def main():
    # Create icons directory if it doesn't exist
    icons_dir = Path(__file__).parent.parent / 'resources' / 'icons'
    icons_dir.mkdir(parents=True, exist_ok=True)
    
    # Default icons (using placeholder icons for now)
    icons = {
        'steam.png': 'https://raw.githubusercontent.com/SteamDatabase/SteamTracking/master/steam.png',
        'discord.png': 'https://raw.githubusercontent.com/discord/discord-api-docs/master/images/discord-logo.png',
        'chrome.png': 'https://raw.githubusercontent.com/google/chrome-logo/master/chrome.png',
        'firefox.png': 'https://raw.githubusercontent.com/mozilla/firefox-logo/master/firefox.png'
    }
    
    for filename, url in icons.items():
        save_path = icons_dir / filename
        if not save_path.exists():
            download_icon(url, save_path)

if __name__ == '__main__':
    main() 