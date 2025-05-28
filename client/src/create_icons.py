from PIL import Image, ImageDraw, ImageFont
import os
from pathlib import Path

def create_icon(text, filename, size=(64, 64), bg_color=(52, 152, 219), text_color=(255, 255, 255)):
    # Create a new image with a white background
    image = Image.new('RGB', size, bg_color)
    draw = ImageDraw.Draw(image)
    
    # Try to load a font, fall back to default if not available
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        font = ImageFont.load_default()
    
    # Calculate text position to center it
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    x = (size[0] - text_width) // 2
    y = (size[1] - text_height) // 2
    
    # Draw the text
    draw.text((x, y), text, font=font, fill=text_color)
    
    # Save the image
    image.save(filename)

def main():
    # Create icons directory if it doesn't exist
    icons_dir = Path(__file__).parent.parent / 'resources' / 'icons'
    icons_dir.mkdir(parents=True, exist_ok=True)
    
    # Create icons for each application
    icons = {
        'steam.png': 'Steam',
        'discord.png': 'Discord',
        'chrome.png': 'Chrome',
        'firefox.png': 'Firefox'
    }
    
    for filename, text in icons.items():
        save_path = icons_dir / filename
        if not save_path.exists():
            create_icon(text, save_path)
            print(f"Created {save_path}")

if __name__ == '__main__':
    main() 