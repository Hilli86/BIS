# Anleitung: Angebotsvorlage mit Positionen-Tabelle

## Problem: Positionen-Schleife funktioniert nicht

Für Tabellenzeilen in `docxtpl` gibt es zwei Syntax-Optionen:

## Option 1: Mustache-Syntax ({{#positionen}})

**Wichtig:** Diese Syntax funktioniert nur, wenn die Tags korrekt in der Word-Tabelle platziert sind.

### So geht's:

1. **Erstellen Sie eine Tabelle in Word** mit folgenden Spalten:
   - Pos | Artikel-Nr. | Bezeichnung | Menge | Bemerkung

2. **Header-Zeile:** Normale Tabellenkopfzeile mit den Spaltenüberschriften

3. **Daten-Zeile (wird wiederholt):**
   - **Erste Zelle:** `{{#positionen}}`
   - **Weitere Zellen:** `{{position}}`, `{{artikelnummer}}`, `{{bezeichnung}}`, `{{menge}}`, `{{bemerkung}}`
   - **Letzte Zelle oder nach der Zeile:** `{{/positionen}}`

**Beispiel-Struktur in Word:**
```
| Pos | Artikel-Nr. | Bezeichnung | Menge | Bemerkung |
|-----|-------------|-------------|-------|-----------|
| {{#positionen}} | {{position}} | {{artikelnummer}} | {{bezeichnung}} | {{menge}} | {{bemerkung}} | {{/positionen}} |
```

**WICHTIG:** 
- `{{#positionen}}` muss in der **ersten Zelle** der Datenzeile stehen
- `{{/positionen}}` muss in der **letzten Zelle** der Datenzeile stehen (oder direkt nach der Zeile)
- Die gesamte Zeile wird für jede Position wiederholt

## Option 2: Jinja2-Syntax ({% for %}) - EMPFOHLEN

Diese Syntax ist für Tabellenzeilen optimiert und funktioniert zuverlässiger.

### So geht's:

1. **Erstellen Sie eine Tabelle in Word** mit folgenden Spalten:
   - Pos | Artikel-Nr. | Bezeichnung | Menge | Bemerkung

2. **Header-Zeile:** Normale Tabellenkopfzeile

3. **Daten-Zeile:**
   - **Am Anfang der Zeile (vor der ersten Zelle):** `{% for pos in positionen %}`
   - **In den Zellen:** `{{pos.position}}`, `{{pos.artikelnummer}}`, `{{pos.bezeichnung}}`, `{{pos.menge}}`, `{{pos.bemerkung}}`
   - **Am Ende der Zeile (nach der letzten Zelle):** `{% endfor %}`

**Beispiel-Struktur in Word:**
```
| Pos | Artikel-Nr. | Bezeichnung | Menge | Bemerkung |
|-----|-------------|-------------|-------|-----------|
{% for pos in positionen %}| {{pos.position}} | {{pos.artikelnummer}} | {{pos.bezeichnung}} | {{pos.menge}} | {{pos.bemerkung}} |{% endfor %}
```

**WICHTIG:**
- `{% for pos in positionen %}` muss **vor** der ersten Zelle der Datenzeile stehen
- `{% endfor %}` muss **nach** der letzten Zelle der Datenzeile stehen
- Verwenden Sie `pos.position`, `pos.artikelnummer`, etc. (mit `pos.` Präfix)
- **WICHTIG:** Verwenden Sie `{% for %}` (ohne "tr"), nicht `{%tr for %}`

## Verfügbare Felder in der Schleife

### Mit Mustache-Syntax ({{#positionen}}):
- `{{position}}` - Positionsnummer (1, 2, 3, ...)
- `{{artikelnummer}}` - Bestellnummer/Artikelnummer
- `{{bezeichnung}}` - Bezeichnung des Artikels
- `{{menge}}` - Menge mit Einheit (z.B. "5 Stück", "2.5 kg", "10 m")
- `{{bemerkung}}` - Bemerkung zur Position

### Mit Jinja2-Syntax ({% for pos in positionen %}):
- `{{pos.position}}` - Positionsnummer
- `{{pos.artikelnummer}}` - Bestellnummer/Artikelnummer
- `{{pos.bezeichnung}}` - Bezeichnung
- `{{pos.menge}}` - Menge
- `{{pos.bemerkung}}` - Bemerkung

## Empfehlung

**Verwenden Sie Option 2 (Jinja2-Syntax mit {% for %})**, da diese:
- ✅ Zuverlässiger funktioniert
- ✅ Speziell für Tabellenzeilen entwickelt wurde
- ✅ Weniger fehleranfällig bei der Platzierung ist
- ✅ **Wichtig:** Verwenden Sie `{% for %}` (ohne "tr"), nicht `{%tr for %}`

## Fehlerbehebung

Wenn die Schleife nicht funktioniert:

1. **Prüfen Sie die Platzierung der Tags:**
   - Bei Mustache: `{{#positionen}}` in erster Zelle, `{{/positionen}}` in letzter Zelle
   - Bei Jinja2: `{% for pos in positionen %}` vor der Zeile, `{% endfor %}` nach der Zeile
   - **Wichtig:** Verwenden Sie `{% for %}` (ohne "tr"), nicht `{%tr for %}`

2. **Prüfen Sie die Feldnamen:**
   - Bei Mustache: `{{position}}`, `{{artikelnummer}}`, etc.
   - Bei Jinja2: `{{pos.position}}`, `{{pos.artikelnummer}}`, etc.

3. **Stellen Sie sicher, dass die Tabelle korrekt formatiert ist:**
   - Header-Zeile sollte normal formatiert sein
   - Daten-Zeile sollte die Schleifen-Tags enthalten

4. **Testen Sie mit einfachen Daten:**
   - Erstellen Sie eine Test-Vorlage mit nur 2-3 Positionen
   - Prüfen Sie, ob die Zeilen korrekt wiederholt werden

