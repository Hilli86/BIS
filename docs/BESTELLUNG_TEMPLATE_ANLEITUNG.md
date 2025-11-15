# Anleitung: Bestellungsvorlage mit Positionen-Tabelle und Unterschrift

## Übersicht

Die Bestellungsvorlage verwendet `docxtpl` (python-docx-template) und unterstützt:
- Positionen-Tabelle mit Gesamtpreis pro Position
- Unterschrift als Bild
- Freigabe-Informationen

## Positionen-Tabelle

### Syntax für Tabellenzeilen

**WICHTIG:** `docxtpl` verwendet Jinja2-Syntax, NICHT Mustache!

**Korrekte Syntax (Jinja2):**
```
{% for pos in positionen %}
| {{pos.position}} | {{pos.artikelnummer}} | {{pos.bezeichnung}} | {{pos.menge}} | {{pos.preis}} {{pos.waehrung}} | {{pos.gesamtpreis}} {{pos.waehrung}} |
{% endfor %}
```

**Falsche Syntax (Mustache - funktioniert NICHT):**
```
{{#positionen}}  ❌ FALSCH - verursacht Fehler "'pos' is undefined"
{{position}} | {{artikelnummer}} | ...
{{/positionen}}
```

**WICHTIG:** 
- Verwenden Sie `{% for pos in positionen %}` (Jinja2-Syntax)
- Verwenden Sie `{% for %}` (ohne "tr"), nicht `{%tr for %}`
- Verwenden Sie `{{pos.position}}`, `{{pos.artikelnummer}}`, etc. (mit `pos.` Präfix)

### Verfügbare Felder pro Position

- `{{pos.position}}` - Positionsnummer (1, 2, 3, ...)
- `{{pos.artikelnummer}}` - Bestellnummer/Artikelnummer
- `{{pos.bezeichnung}}` - Bezeichnung des Artikels
- `{{pos.menge}}` - Menge mit Einheit (z.B. "5 Stück", "2.5 kg", "10 m")
- `{{pos.preis}}` - Einzelpreis (mit 2 Kommastellen)
- `{{pos.gesamtpreis}}` - Gesamtpreis pro Position (Menge × Preis, mit 2 Kommastellen)
- `{{pos.waehrung}}` - Währung (z.B. "EUR", "USD", "CHF")

### Gesamtbetrag

- `{{gesamtbetrag}}` - Gesamtbetrag aller Positionen (mit 2 Kommastellen)
- `{{waehrung}}` - Währung des Gesamtbetrags

## Unterschrift einfügen

### So fügen Sie die Unterschrift in Word ein:

**WICHTIG:** Die Unterschrift muss als einfacher Platzhalter `{{unterschrift}}` eingefügt werden, NICHT in Anführungszeichen oder als Text!

1. **Platzhalter in Word einfügen:**
   - Platzieren Sie den Cursor an der gewünschten Stelle (z.B. am Ende des Dokuments)
   - Geben Sie ein: `{% if hat_unterschrift %}{{unterschrift}}{% endif %}`
   - **WICHTIG:** Stellen Sie sicher, dass `{{unterschrift}}` als Platzhalter erkannt wird (nicht als normaler Text)

2. **Alternative mit Bedingung:**
   ```
   {% if hat_unterschrift %}
   {{unterschrift}}
   {% endif %}
   ```

3. **Mit zusätzlichen Informationen:**
   ```
   {% if hat_unterschrift %}
   {{unterschrift}}
   
   {{freigegeben_von}}
   {% if freigegeben_von_abteilung %}
   {{freigegeben_von_abteilung}}
   {% endif %}
   Freigegeben am: {{freigegeben_am}}
   {% endif %}
   ```

**WICHTIG:**
- Die Unterschrift wird automatisch als Bild eingefügt (80mm Breite)
- Die Höhe wird automatisch angepasst
- Die Unterschrift wird nur angezeigt, wenn `hat_unterschrift` true ist
- **Stellen Sie sicher, dass `{{unterschrift}}` direkt im Text steht, nicht in einer Tabelle oder einem Textfeld**
- Falls die Unterschrift nicht angezeigt wird, prüfen Sie:
  1. Ob `hat_unterschrift` true ist (Unterschrift vorhanden)
  2. Ob der Platzhalter `{{unterschrift}}` korrekt geschrieben ist
  3. Ob die Bedingung `{% if hat_unterschrift %}` korrekt ist

## Verfügbare Template-Variablen

### Bestellungs-Daten
- `{{bestellung_id}}` - ID der Bestellung
- `{{bestellnummer}}` - Bestellnummer
- `{{datum}}` - Erstellungsdatum (Format: DD.MM.YYYY)
- `{{erstellt_von}}` - Name des Erstellers
- `{{erstellt_von_kontakt}}` - Kontaktdaten des Erstellers (E-Mail, Tel)
- `{{status}}` - Status der Bestellung
- `{{bemerkung}}` - Bemerkung zur Bestellung
- `{{freigabe_bemerkung}}` - Bemerkung zur Freigabe

### Lieferant-Daten
- `{{lieferant_name}}`
- `{{lieferant_strasse}}`
- `{{lieferant_plz}}`
- `{{lieferant_ort}}`
- `{{lieferant_plz_ort}}` - PLZ und Ort kombiniert
- `{{lieferant_telefon}}`
- `{{lieferant_email}}`

### Firmendaten
- `{{firmenname}}`
- `{{firmenstrasse}}`
- `{{firmenplz}}`
- `{{firmenort}}`
- `{{firmenplz_ort}}` - PLZ und Ort kombiniert
- `{{firmen_telefon}}`
- `{{firmen_website}}`
- `{{firmen_email}}`
- `{{firma_lieferstraße}}` - Lieferstraße
- `{{firma_lieferPLZ}}` - Liefer-PLZ
- `{{firma_lieferOrt}}` - Liefer-Ort
- `{{lieferanschrift}}` - Lieferanschrift (falls abweichend)
- `{{footer}}` - Footer-Informationen

### Positionen
- `{{positionen}}` - Liste der Positionen (für Schleife)
- `{{hat_positionen}}` - Boolean, ob Positionen vorhanden sind
- `{{gesamtbetrag}}` - Gesamtbetrag aller Positionen
- `{{waehrung}}` - Währung

### Freigabe-Daten
- `{{freigegeben_von}}` - Name des Freigebers
- `{{freigegeben_von_abteilung}}` - Abteilung des Freigebers
- `{{freigegeben_am}}` - Freigabedatum (Format: DD.MM.YYYY HH:MM)
- `{{hat_unterschrift}}` - Boolean, ob Unterschrift vorhanden ist
- `{{unterschrift}}` - Unterschrift als Bild (InlineImage)

## Beispiel-Tabellenstruktur

```
| Pos | Artikel-Nr. | Bezeichnung | Menge | Preis | Gesamt |
|-----|-------------|-------------|-------|-------|--------|
{% for pos in positionen %}| {{pos.position}} | {{pos.artikelnummer}} | {{pos.bezeichnung}} | {{pos.menge}} | {{pos.preis}} {{pos.waehrung}} | {{pos.gesamtpreis}} {{pos.waehrung}} |{% endfor %}
|     |             |             |       |       | Gesamt: {{gesamtbetrag}} {{waehrung}} |
```

## Bedingungen

Sie können Bedingungen verwenden. **WICHTIG:** `docxtpl` verwendet Jinja2-Syntax, nicht Mustache!

**Korrekte Syntax (Jinja2):**
```
{% if hat_unterschrift %}
Unterschrift:
{{unterschrift}}
{% endif %}

{% if freigabe_bemerkung %}
Freigabebemerkung: {{freigabe_bemerkung}}
{% endif %}
```

**Falsche Syntax (Mustache - funktioniert NICHT):**
```
{{#if hat_unterschrift}}  ❌ FALSCH
{{unterschrift}}
{{/if}}
```

**Verfügbare Bedingungsoperatoren:**
- `{% if variable %}` - Wenn Variable vorhanden/true ist
- `{% if not variable %}` - Wenn Variable nicht vorhanden/false ist
- `{% if variable == 'wert' %}` - Wenn Variable gleich Wert ist
- `{% if variable and andere_variable %}` - UND-Verknüpfung
- `{% if variable or andere_variable %}` - ODER-Verknüpfung

## Fehlerbehebung

### Fehler: "'pos' is undefined"

**Ursache:** Sie verwenden Mustache-Syntax statt Jinja2-Syntax.

**Lösung:** 
- ❌ Falsch: `{{#positionen}}...{{/positionen}}`
- ✅ Richtig: `{% for pos in positionen %}...{% endfor %}`

**Prüfen Sie Ihre Word-Vorlage:**
1. Öffnen Sie die Vorlage in Word
2. Suchen Sie nach `{{#positionen}}` oder `{{#if positionen}}`
3. Ersetzen Sie durch `{% for pos in positionen %}`
4. Ersetzen Sie `{{/positionen}}` durch `{% endfor %}`
5. Stellen Sie sicher, dass Sie `{{pos.position}}` statt `{{position}}` verwenden

### Fehler: "unexpected char '#'"

**Ursache:** Sie verwenden Mustache-Syntax (`{{#if}}`) statt Jinja2-Syntax (`{% if %}`).

**Lösung:**
- ❌ Falsch: `{{#if hat_unterschrift}}...{{/if}}`
- ✅ Richtig: `{% if hat_unterschrift %}...{% endif %}`

## Tipps

1. **Tabellenformatierung:** Formatieren Sie die Tabelle in Word wie gewünscht. Die Formatierung bleibt erhalten.

2. **Unterschrift-Größe:** Die Unterschrift wird mit 80mm Breite eingefügt. Falls Sie eine andere Größe benötigen, können Sie dies im Code anpassen (Zeile mit `InlineImage(doc, tmp_img_path, width=80)`).

3. **Leere Felder:** Wenn ein Feld leer ist, wird ein leerer String zurückgegeben. Verwenden Sie Bedingungen, um leere Felder zu verstecken.

4. **Währung:** Die Währung wird aus den Positionen übernommen. Alle Positionen sollten die gleiche Währung haben.

5. **Syntax-Checkliste:**
   - ✅ Schleifen: `{% for pos in positionen %}...{% endfor %}`
   - ✅ Bedingungen: `{% if variable %}...{% endif %}`
   - ✅ Variablen: `{{variable}}` oder `{{pos.position}}`
   - ❌ KEINE Mustache-Syntax: `{{#if}}`, `{{#positionen}}`, etc.

