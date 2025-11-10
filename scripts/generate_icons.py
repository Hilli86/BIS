"""
Icon-Generator für BIS PWA
Generiert PNG-Icons in verschiedenen Größen aus dem SVG-Logo

Voraussetzungen:
  pip install Pillow cairosvg

Verwendung:
  python generate_icons.py
"""

import os
from pathlib import Path

try:
    import cairosvg
    from PIL import Image
    import io
except ImportError:
    print("\n[FEHLER] Benötigte Module nicht installiert.")
    print("\nBitte installieren Sie:")
    print("  pip install Pillow cairosvg")
    print("\nFür Windows zusätzlich GTK3 Runtime erforderlich:")
    print("  https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases")
    exit(1)

# Icon-Größen
ICON_SIZES = [32, 120, 152, 180, 192, 512]

# Pfade
SCRIPT_DIR = Path(__file__).parent
SVG_PATH = SCRIPT_DIR / 'static' / 'icons' / 'logo.svg'
ICONS_DIR = SCRIPT_DIR / 'static' / 'icons'

def generate_icons():
    """Generiert PNG-Icons aus dem SVG"""
    
    # Erstelle Icons-Verzeichnis falls nicht vorhanden
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("  BIS - Icon Generator")
    print("=" * 70)
    print()
    
    if not SVG_PATH.exists():
        print(f"[FEHLER] SVG-Datei nicht gefunden: {SVG_PATH}")
        return
    
    # Lese SVG
    with open(SVG_PATH, 'r', encoding='utf-8') as f:
        svg_data = f.read()
    
    # Generiere Icons in verschiedenen Größen
    for size in ICON_SIZES:
        output_path = ICONS_DIR / f'icon-{size}.png'
        
        try:
            # Konvertiere SVG zu PNG
            png_data = cairosvg.svg2png(
                bytestring=svg_data.encode('utf-8'),
                output_width=size,
                output_height=size
            )
            
            # Speichere PNG
            with open(output_path, 'wb') as f:
                f.write(png_data)
            
            print(f"[OK] Icon erstellt: icon-{size}.png ({size}x{size}px)")
            
        except Exception as e:
            print(f"[FEHLER] Icon {size}x{size}: {str(e)}")
    
    print()
    print("=" * 70)
    print("  Icons erfolgreich generiert!")
    print("=" * 70)
    print()

if __name__ == '__main__':
    generate_icons()

