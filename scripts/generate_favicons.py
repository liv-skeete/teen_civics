"""
Generate favicon files from the main icon image.
"""
from PIL import Image
import os

# Paths
icon_path = 'static/icon-removebg-preview.png'
static_dir = 'static'

# Open the original icon
img = Image.open(icon_path)

# Convert to RGBA if not already
if img.mode != 'RGBA':
    img = img.convert('RGBA')

# Generate favicon.ico (16x16 and 32x32 combined)
favicon_sizes = [(16, 16), (32, 32)]
favicon_images = []
for size in favicon_sizes:
    resized = img.resize(size, Image.Resampling.LANCZOS)
    favicon_images.append(resized)

favicon_images[0].save(
    os.path.join(static_dir, 'favicon.ico'),
    format='ICO',
    sizes=[(16, 16), (32, 32)]
)
print("✓ Generated favicon.ico")

# Generate favicon-16x16.png
img_16 = img.resize((16, 16), Image.Resampling.LANCZOS)
img_16.save(os.path.join(static_dir, 'favicon-16x16.png'), format='PNG')
print("✓ Generated favicon-16x16.png")

# Generate favicon-32x32.png
img_32 = img.resize((32, 32), Image.Resampling.LANCZOS)
img_32.save(os.path.join(static_dir, 'favicon-32x32.png'), format='PNG')
print("✓ Generated favicon-32x32.png")

# Generate apple-touch-icon.png (180x180 is standard)
img_apple = img.resize((180, 180), Image.Resampling.LANCZOS)
img_apple.save(os.path.join(static_dir, 'apple-touch-icon.png'), format='PNG')
print("✓ Generated apple-touch-icon.png")

print("\nAll favicon files generated successfully!")