"""
Einfacher Icon-Generator für BIS PWA (ohne SVG-Bibliotheken)
Erstellt einfache Icons mit PIL/Pillow

Voraussetzungen:
  pip install Pillow

Verwendung:
  python generate_icons_simple.py
"""

import os
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("\n[FEHLER] Pillow nicht installiert.")
    print("\nBitte installieren Sie:")
    print("  pip install Pillow")
    exit(1)

# Icon-Größen
ICON_SIZES = [32, 120, 152, 180, 192, 512]

# Pfade
SCRIPT_DIR = Path(__file__).parent
ICONS_DIR = SCRIPT_DIR / 'static' / 'icons'

def draw_fish(draw, width, height, scale=1.0):
    """Zeichnet einen einfachen Fisch"""
    # Skalierungsfaktor anwenden
    s = scale
    cx, cy = width // 2, height // 2
    
    # Fisch-Körper (Ellipse)
    body_width = int(140 * s)
    body_height = int(85 * s)
    draw.ellipse([
        cx - body_width//2, cy - body_height//2,
        cx + body_width//2, cy + body_height//2
    ], fill='white')
    
    # Fisch-Kopf (Kreis)
    head_radius = int(70 * s)
    head_x = cx - int(140 * s)
    draw.ellipse([
        head_x - head_radius, cy - head_radius,
        head_x + head_radius, cy + head_radius
    ], fill='white')
    
    # Auge
    eye_radius = int(12 * s)
    eye_x = head_x - int(20 * s)
    eye_y = cy - int(16 * s)
    draw.ellipse([
        eye_x - eye_radius, eye_y - eye_radius,
        eye_x + eye_radius, eye_y + eye_radius
    ], fill='#0066cc')
    
    # Schwanzflosse (Dreieck)
    tail_x = cx + body_width//2
    tail_size = int(70 * s)
    draw.polygon([
        (tail_x, cy),
        (tail_x + tail_size, cy - tail_size//2),
        (tail_x + tail_size, cy + tail_size//2)
    ], fill='white')
    
    # Obere Rückenflosse (Dreieck)
    fin_top_x = cx - int(20 * s)
    fin_top_y = cy - body_height//2
    fin_size = int(50 * s)
    draw.polygon([
        (fin_top_x - fin_size//2, fin_top_y),
        (fin_top_x, fin_top_y - fin_size),
        (fin_top_x + fin_size//2, fin_top_y)
    ], fill='white')
    
    # Untere Bauchflosse (Dreieck)
    fin_bottom_y = cy + body_height//2
    draw.polygon([
        (fin_top_x - fin_size//2, fin_bottom_y),
        (fin_top_x, fin_bottom_y + fin_size),
        (fin_top_x + fin_size//2, fin_bottom_y)
    ], fill='white')

def generate_icon(size):
    """Generiert ein Icon in der angegebenen Größe"""
    # Erstelle neues Bild mit blauem Hintergrund
    img = Image.new('RGB', (size, size), '#0066cc')
    draw = ImageDraw.Draw(img)
    
    # Zeichne Fisch (skaliert basierend auf Icon-Größe)
    scale = size / 512  # Referenzgröße ist 512x512
    draw_fish(draw, size, size, scale)
    
    return img

def generate_icons():
    """Generiert PNG-Icons in verschiedenen Größen"""
    
    # Erstelle Icons-Verzeichnis falls nicht vorhanden
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("  BIS - Icon Generator (Simple)")
    print("=" * 70)
    print()
    
    # Generiere Icons in verschiedenen Größen
    for size in ICON_SIZES:
        output_path = ICONS_DIR / f'icon-{size}.png'
        
        try:
            img = generate_icon(size)
            img.save(output_path, 'PNG', optimize=True)
            print(f"[OK] Icon erstellt: icon-{size}.png ({size}x{size}px)")
            
        except Exception as e:
            print(f"[FEHLER] Icon {size}x{size}: {str(e)}")
    
    print()
    print("=" * 70)
    print("  Icons erfolgreich generiert!")
    print("=" * 70)
    print()
    print(f"Icons gespeichert in: {ICONS_DIR}")
    print()

if __name__ == '__main__':
    generate_icons()

