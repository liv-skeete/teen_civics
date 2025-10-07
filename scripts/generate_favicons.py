#!/usr/bin/env python3
"""
Generate favicon files from logo.png
Creates multiple sizes for different use cases
"""

from PIL import Image
import os

def generate_favicons():
    """Generate all favicon sizes from logo.png"""
    
    # Paths
    logo_path = 'static/img/logo.png'
    static_dir = 'static'
    
    # Check if logo exists
    if not os.path.exists(logo_path):
        print(f"Error: {logo_path} not found!")
        return False
    
    print(f"Loading logo from {logo_path}...")
    logo = Image.open(logo_path)
    
    # Convert to RGBA if not already
    if logo.mode != 'RGBA':
        logo = logo.convert('RGBA')
    
    print(f"Original logo size: {logo.size}")
    
    # Define favicon sizes to generate
    favicon_sizes = [
        ('favicon-16x16.png', (16, 16)),
        ('favicon-32x32.png', (32, 32)),
        ('apple-touch-icon.png', (180, 180)),
    ]
    
    # Generate PNG favicons
    for filename, size in favicon_sizes:
        output_path = os.path.join(static_dir, filename)
        print(f"Creating {filename} at {size}...")
        
        # Resize with high-quality resampling
        resized = logo.resize(size, Image.Resampling.LANCZOS)
        
        # Save as PNG
        resized.save(output_path, 'PNG', optimize=True)
        print(f"  ✓ Saved to {output_path}")
    
    # Generate multi-resolution favicon.ico
    # ICO format can contain multiple sizes
    ico_path = os.path.join(static_dir, 'favicon.ico')
    print(f"Creating favicon.ico with multiple resolutions...")
    
    # Create images at different sizes for the ICO file
    ico_sizes = [(16, 16), (32, 32), (48, 48)]
    ico_images = []
    
    for size in ico_sizes:
        resized = logo.resize(size, Image.Resampling.LANCZOS)
        ico_images.append(resized)
    
    # Save as ICO with multiple sizes
    ico_images[0].save(
        ico_path,
        format='ICO',
        sizes=ico_sizes,
        append_images=ico_images[1:]
    )
    print(f"  ✓ Saved to {ico_path}")
    
    print("\n✅ All favicon files generated successfully!")
    print("\nGenerated files:")
    for filename, _ in favicon_sizes:
        print(f"  - static/{filename}")
    print(f"  - static/favicon.ico")
    
    return True

if __name__ == '__main__':
    success = generate_favicons()
    exit(0 if success else 1)