#!/usr/bin/env python3
"""
Generate favicon PNG files from icon.png
This script creates favicon files in various sizes needed for web browsers and devices.
"""

from PIL import Image
import os

def generate_favicons():
    """Generate favicon PNG files from icon.png"""
    
    # Define the source icon and output directory
    source_icon = "static/icon.png"
    output_dir = "static"
    
    # Check if source icon exists
    if not os.path.exists(source_icon):
        print(f"Error: Source icon '{source_icon}' not found!")
        return False
    
    # Define favicon sizes to generate
    favicon_sizes = {
        "favicon-16x16.png": (16, 16),
        "favicon-32x32.png": (32, 32),
        "apple-touch-icon.png": (180, 180),
    }
    
    try:
        # Open the source icon
        print(f"Opening source icon: {source_icon}")
        icon = Image.open(source_icon)
        
        # Convert to RGBA if not already (to preserve transparency)
        if icon.mode != 'RGBA':
            icon = icon.convert('RGBA')
        
        print(f"Source icon size: {icon.size}")
        print(f"Source icon mode: {icon.mode}")
        
        # Generate each favicon size
        for filename, size in favicon_sizes.items():
            output_path = os.path.join(output_dir, filename)
            
            # Resize the icon using high-quality resampling
            resized_icon = icon.resize(size, Image.Resampling.LANCZOS)
            
            # Save the resized icon
            resized_icon.save(output_path, "PNG", optimize=True)
            print(f"✓ Generated: {output_path} ({size[0]}x{size[1]})")
        
        print("\n✅ All favicon PNG files generated successfully!")
        print("\nNote: favicon.ico was not regenerated (requires special handling).")
        print("If you need a .ico file, use an online converter or specialized tool.")
        
        return True
        
    except Exception as e:
        print(f"❌ Error generating favicons: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Favicon Generator for TeenCivics")
    print("=" * 60)
    print()
    
    success = generate_favicons()
    
    if success:
        print("\n" + "=" * 60)
        print("Done! Your favicon PNG files have been updated.")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("Failed to generate favicons. Please check the error above.")
        print("=" * 60)