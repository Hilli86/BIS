# Berichtsdesigner - Visuelle Berichtserstellung

## Übersicht

Dieses Dokument beschreibt verschiedene Möglichkeiten, Berichte mit einem visuellen Designer zu erstellen, sodass Design-Änderungen ohne Code-Anpassungen möglich sind.

## Option 1: Word-Templates mit python-docx-template (EMPFOHLEN)

### Vorteile
- ✅ Word als Designer (jeder kennt Word)
- ✅ Platzhalter für dynamische Daten
- ✅ Keine Code-Änderungen für Design-Anpassungen
- ✅ Einfache Integration
- ✅ Unterstützt Tabellen, Bilder, Formatierung

### Installation

```bash
pip install python-docx-template
```

### Verwendung

1. **Word-Template erstellen** (`templates/reports/bestellung_template.docx`):
   - Erstellen Sie ein Word-Dokument mit Platzhaltern:
     - `{{firmenname}}` - Einfache Variablen
     - `{{#positionen}}...{{/positionen}}` - Schleifen
     - `{{#if status}}...{{/if}}` - Bedingungen

2. **Python-Code** (Beispiel für Bestellung):

```python
from docxtpl import DocxTemplate
from io import BytesIO

def bestellung_pdf_export_word_template(bestellung_id):
    """PDF-Export mit Word-Template"""
    # Daten aus Datenbank laden (wie bisher)
    with get_db_connection() as conn:
        bestellung = conn.execute("SELECT * FROM Bestellung WHERE ID = ?", (bestellung_id,)).fetchone()
        positionen = conn.execute("SELECT * FROM BestellungPosition WHERE BestellungID = ?", (bestellung_id,)).fetchall()
        firmendaten = get_firmendaten()
    
    # Template laden
    template_path = os.path.join(current_app.root_path, 'templates', 'reports', 'bestellung_template.docx')
    doc = DocxTemplate(template_path)
    
    # Kontext für Template
    context = {
        'firmenname': firmendaten['Firmenname'],
        'firmenstrasse': firmendaten['Strasse'],
        'firmenplz': firmendaten['PLZ'],
        'firmenort': firmendaten['Ort'],
        'bestellnummer': bestellung['Bestellnummer'],
        'datum': bestellung['ErstelltAm'].strftime('%d.%m.%Y'),
        'lieferant_name': bestellung['LieferantName'],
        'positionen': [
            {
                'bestellnummer': p['Bestellnummer'],
                'bezeichnung': p['Bezeichnung'],
                'menge': p['Menge'],
                'einheit': p['Einheit'],
                'preis': p['Preis'],
                'gesamt': p['Menge'] * p['Preis']
            }
            for p in positionen
        ],
        'gesamtpreis': sum(p['Menge'] * p['Preis'] for p in positionen)
    }
    
    # Template rendern
    doc.render(context)
    
    # Als PDF speichern (benötigt LibreOffice oder docx2pdf)
    # Oder als DOCX zurückgeben
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    
    return buffer
```

### Template-Beispiel (Word-Dokument)

```
ANGEBOTSANFRAGE

Von: {{firmenname}}
     {{firmenstrasse}}
     {{firmenplz}} {{firmenort}}

An: {{lieferant_name}}

Datum: {{datum}}
Bestellnummer: {{bestellnummer}}

Positionen:
{% for pos in positionen %}
{{pos.bestellnummer}} | {{pos.bezeichnung}} | {{pos.menge}} {{pos.einheit}} | {{pos.preis}} €
{% endfor %}

Gesamtpreis: {{gesamtpreis}} €
```

### PDF-Konvertierung

Für PDF-Export benötigen Sie zusätzlich:
- **Option A**: `docx2pdf` (benötigt Microsoft Word oder LibreOffice)
- **Option B**: Als DOCX zurückgeben, Browser konvertiert zu PDF
- **Option C**: `python-docx` + `reportlab` (komplexer)

```bash
pip install docx2pdf
```

---

## Option 2: ReportBro - Professioneller Berichtsdesigner

### Vorteile
- ✅ Visueller Designer im Browser
- ✅ Sehr professionell
- ✅ Direkte PDF-Generierung
- ✅ Komplexe Layouts möglich

### Nachteile
- ⚠️ Mehr Setup-Aufwand
- ⚠️ Community-Version limitiert, Pro-Version kostenpflichtig

### Installation

```bash
pip install reportbro-lib
```

### Integration

1. **ReportBro Designer Route hinzufügen**:

```python
from reportbro import Report, ReportBro

@app.route('/admin/report-designer')
@admin_required
def report_designer():
    """ReportBro Designer Interface"""
    return render_template('admin/report_designer.html')
```

2. **Report generieren**:

```python
from reportbro import Report

def generate_report(report_definition, data):
    """Generiert PDF aus ReportBro Definition"""
    report = Report(report_definition, data)
    pdf_bytes = report.generate_pdf()
    return pdf_bytes
```

### Weitere Informationen
- Website: https://www.reportbro.com/
- Dokumentation: https://www.reportbro.com/documentation/

---

## Option 3: HTML/Jinja2 Templates + WeasyPrint

### Vorteile
- ✅ HTML/CSS als Designer (flexibel)
- ✅ Jinja2-Platzhalter (bereits bekannt)
- ✅ Keine zusätzlichen Tools nötig

### Nachteile
- ⚠️ Kein visueller Designer (nur HTML-Editierung)
- ⚠️ PDF-Rendering kann komplex sein

### Installation

```bash
pip install weasyprint
```

### Verwendung

1. **HTML-Template erstellen** (`templates/reports/bestellung.html`):

```html
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial; }
        .header { text-align: right; }
        .position-table { width: 100%; border-collapse: collapse; }
        .position-table th, .position-table td { border: 1px solid #ddd; padding: 8px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{firmenname}}</h1>
        <p>{{firmenstrasse}}<br>{{firmenplz}} {{firmenort}}</p>
    </div>
    
    <h2>Bestellung {{bestellnummer}}</h2>
    <p>Datum: {{datum}}</p>
    
    <table class="position-table">
        <thead>
            <tr>
                <th>Bestellnummer</th>
                <th>Bezeichnung</th>
                <th>Menge</th>
                <th>Preis</th>
            </tr>
        </thead>
        <tbody>
            {% for pos in positionen %}
            <tr>
                <td>{{pos.bestellnummer}}</td>
                <td>{{pos.bezeichnung}}</td>
                <td>{{pos.menge}} {{pos.einheit}}</td>
                <td>{{pos.preis}} €</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    
    <p><strong>Gesamtpreis: {{gesamtpreis}} €</strong></p>
</body>
</html>
```

2. **Python-Code**:

```python
from weasyprint import HTML
from flask import render_template_string

def bestellung_pdf_export_html(bestellung_id):
    """PDF-Export mit HTML-Template"""
    # Daten laden
    with get_db_connection() as conn:
        bestellung = conn.execute("SELECT * FROM Bestellung WHERE ID = ?", (bestellung_id,)).fetchone()
        # ... weitere Daten
    
    # HTML rendern
    html_content = render_template('reports/bestellung.html', 
                                   bestellung=bestellung,
                                   positionen=positionen,
                                   firmendaten=firmendaten)
    
    # PDF generieren
    pdf_bytes = HTML(string=html_content).write_pdf()
    
    return pdf_bytes
```

---

## Option 4: Excel-Templates mit openpyxl

### Vorteile
- ✅ Excel als Designer
- ✅ Komplexe Berechnungen möglich
- ✅ Tabellen-Formatierung einfach

### Installation

```bash
pip install openpyxl
```

### Verwendung

Ähnlich wie Word-Templates, aber mit Excel-Dateien. Platzhalter werden durch Python ersetzt.

---

## Empfehlung

**Für Ihre Anwendung empfehle ich Option 1 (Word-Templates)**:

1. ✅ Einfachste Integration
2. ✅ Jeder kann Word-Templates bearbeiten
3. ✅ Keine zusätzlichen Server-Komponenten nötig
4. ✅ Funktioniert gut mit bestehender Flask-App

### Migrations-Strategie

1. Erstellen Sie Word-Templates für bestehende PDF-Exporte
2. Implementieren Sie die neue Route parallel zur alten
3. Testen Sie beide Varianten
4. Wechseln Sie schrittweise um

### Beispiel-Integration

Siehe `modules/ersatzteile/routes_template_example.py` für ein vollständiges Beispiel.

---

## Weitere Ressourcen

- **python-docx-template**: https://github.com/elapouya/python-docx-template
- **ReportBro**: https://www.reportbro.com/
- **WeasyPrint**: https://weasyprint.org/
- **Jinja2 Templates**: https://jinja.palletsprojects.com/

