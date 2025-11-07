# BIS Icons und Logo

Dieses Verzeichnis enthält alle Icons und Logos für die BIS Progressive Web App.

## 📁 Dateien

- **logo.svg**: Vektorgrafik des BIS-Logos (weißer Fisch auf blauem Hintergrund)
- **icon-32.png**: Favicon (32x32px)
- **icon-120.png**: iOS Home Screen Icon (120x120px)
- **icon-152.png**: iOS Home Screen Icon für iPad (152x152px)
- **icon-180.png**: iOS Home Screen Icon für iPhone (180x180px)
- **icon-192.png**: Android Home Screen Icon (192x192px)
- **icon-512.png**: Hochauflösendes Icon für Splash Screens (512x512px)

## 🎨 Design

Das BIS-Logo zeigt einen **weißen Fisch** (#ffffff) auf **blauem Hintergrund** (#0066cc).

Das Design ist:
- Einfach und einprägsam
- Gut erkennbar in kleinen Größen
- Optimiert für verschiedene Plattformen (iOS, Android, Desktop)

## 🔄 Icons neu generieren

Falls Sie die Icons ändern oder neu generieren möchten:

### Methode 1: Einfaches Python-Script (empfohlen)

```bash
py generate_icons_simple.py
```

**Voraussetzungen:**
```bash
pip install Pillow
```

### Methode 2: SVG-basiertes Script (bessere Qualität)

```bash
py generate_icons.py
```

**Voraussetzungen:**
```bash
pip install Pillow cairosvg
```

**Hinweis für Windows**: Für CairoSVG wird zusätzlich GTK3 Runtime benötigt:
https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases

### Logo-SVG bearbeiten

Sie können die Datei `logo.svg` mit einem beliebigen SVG-Editor (z.B. Inkscape, Adobe Illustrator) bearbeiten und dann die Icons neu generieren.

## 🖼️ Icon-Größen und Verwendung

| Größe | Verwendung |
|-------|-----------|
| 32x32 | Browser-Favicon |
| 120x120 | iOS Home Screen (iPhone) |
| 152x152 | iOS Home Screen (iPad) |
| 180x180 | iOS Home Screen (iPhone Retina) |
| 192x192 | Android Home Screen |
| 512x512 | Splash Screen, hochauflösende Displays |

## 📱 Plattform-Unterstützung

- ✅ **iOS (Safari)**: Apple Touch Icons werden unterstützt
- ✅ **Android (Chrome)**: Web App Manifest Icons werden verwendet
- ✅ **Desktop (Chrome, Edge, Firefox)**: PWA-Icons im Browser
- ✅ **Windows**: Als Desktop-App installierbar

## 🔗 Verwendung im Code

Die Icons werden im `base.html` Template referenziert:

```html
<!-- iOS -->
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/icon-180.png">

<!-- Standard -->
<link rel="icon" type="image/png" sizes="192x192" href="/static/icons/icon-192.png">

<!-- Manifest -->
<link rel="manifest" href="/static/manifest.json">
```

Im `manifest.json` sind alle Icon-Größen definiert und werden von unterstützten Browsern automatisch verwendet.

