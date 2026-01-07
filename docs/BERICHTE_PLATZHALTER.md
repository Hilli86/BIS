# Berichte - Template-Platzhalter Übersicht

Diese Dokumentation listet alle verfügbaren Platzhalter für die Word-Vorlagen der verschiedenen Berichttypen auf.

## Wichtige Hinweise

- **Syntax:** Alle Templates verwenden **Jinja2-Syntax** (`{% %}` für Kontrollstrukturen, `{{ }}` für Variablen)
- **Schleifen:** Verwenden Sie `{% for item in liste %}` ... `{% endfor %}`
- **Bedingungen:** Verwenden Sie `{% if variable %}` ... `{% endif %}`
- **Tabellen:** Bei Tabellenzeilen steht `{% for %}` **vor** der ersten Zelle, `{% endfor %}` **nach** der letzten Zelle

---

## 1. Bestellung (`bestellung_template.docx`)

### Bestellungs-Daten

| Platzhalter | Beschreibung | Format |
|------------|-------------|--------|
| `{{bestellung_id}}` | ID der Bestellung | Zahl |
| `{{bestellnummer}}` | Bestellnummer | Text |
| `{{datum}}` | Erstellungsdatum | DD.MM.YYYY |
| `{{erstellt_von}}` | Name des Erstellers | Text |
| `{{erstellt_von_kontakt}}` | Kontaktdaten (E-Mail, Tel) | Text |
| `{{status}}` | Status der Bestellung | Text |
| `{{bemerkung}}` | Bemerkung zur Bestellung | Text |
| `{{freigabe_bemerkung}}` | Bemerkung zur Freigabe | Text |

### Lieferant-Daten

| Platzhalter | Beschreibung | Format |
|------------|-------------|--------|
| `{{lieferant_name}}` | Name des Lieferanten | Text |
| `{{lieferant_strasse}}` | Straße | Text |
| `{{lieferant_plz}}` | Postleitzahl | Text |
| `{{lieferant_ort}}` | Ort | Text |
| `{{lieferant_plz_ort}}` | PLZ und Ort kombiniert | Text |
| `{{lieferant_telefon}}` | Telefonnummer | Text |
| `{{lieferant_email}}` | E-Mail-Adresse | Text |

### Positionen

**Schleife für Positionen:**
```
{% for pos in positionen %}
| {{pos.position}} | {{pos.artikelnummer}} | {{pos.bezeichnung}} | {{pos.menge}} | {{pos.preis}} {{pos.waehrung}} | {{pos.gesamtpreis}} {{pos.waehrung}} |
{% endfor %}
```

**Felder pro Position:**
- `{{pos.position}}` - Positionsnummer (1, 2, 3, ...)
- `{{pos.artikelnummer}}` - Bestellnummer/Artikelnummer
- `{{pos.bezeichnung}}` - Bezeichnung des Artikels
- `{{pos.menge}}` - Menge mit Einheit (z.B. "5 Stück", "2.5 kg")
- `{{pos.preis}}` - Einzelpreis (mit 2 Kommastellen, z.B. "10.50")
- `{{pos.gesamtpreis}}` - Gesamtpreis pro Position (mit 2 Kommastellen)
- `{{pos.waehrung}}` - Währung (z.B. "EUR", "USD")

**Gesamtbetrag:**
- `{{gesamtbetrag}}` - Gesamtbetrag aller Positionen (mit 2 Kommastellen)
- `{{waehrung}}` - Währung des Gesamtbetrags
- `{{hat_positionen}}` - Boolean, ob Positionen vorhanden sind

### Freigabe-Daten

| Platzhalter | Beschreibung | Format |
|------------|-------------|--------|
| `{{freigegeben_von}}` | Name des Freigebers | Text |
| `{{freigegeben_von_abteilung}}` | Abteilung des Freigebers | Text |
| `{{freigegeben_am}}` | Freigabedatum | DD.MM.YYYY HH:MM |
| `{{hat_unterschrift}}` | Boolean, ob Unterschrift vorhanden ist | true/false |
| `{{unterschrift}}` | Unterschrift als Bild (InlineImage) | Bild |

**Unterschrift einfügen:**
```
{% if hat_unterschrift %}
{{unterschrift}}
{% endif %}
```

### Firmendaten

| Platzhalter | Beschreibung | Format |
|------------|-------------|--------|
| `{{firmenname}}` | Firmenname | Text |
| `{{firmenstrasse}}` | Straße | Text |
| `{{firmenplz}}` | Postleitzahl | Text |
| `{{firmenort}}` | Ort | Text |
| `{{firmenplz_ort}}` | PLZ und Ort kombiniert | Text |
| `{{firmen_telefon}}` | Telefonnummer | Text |
| `{{firmen_website}}` | Website | Text |
| `{{firmen_email}}` | E-Mail-Adresse | Text |
| `{{firma_lieferstraße}}` | Lieferstraße (falls abweichend) | Text |
| `{{firma_lieferPLZ}}` | Liefer-PLZ | Text |
| `{{firma_lieferOrt}}` | Liefer-Ort | Text |
| `{{lieferanschrift}}` | Lieferanschrift (mehrzeilig) | Text |
| `{{footer}}` | Footer-Informationen (Geschäftsführer, UStIdNr, etc.) | Text |

---

## 2. Angebotsanfrage (`angebot_template.docx`)

### Angebotsanfrage-Daten

| Platzhalter | Beschreibung | Format |
|------------|-------------|--------|
| `{{angebotsanfrage_id}}` | ID der Angebotsanfrage | Zahl |
| `{{datum}}` | Erstellungsdatum | DD.MM.YYYY |
| `{{erstellt_von}}` | Name des Erstellers | Text |
| `{{erstellt_von_abteilung}}` | Abteilung des Erstellers | Text |
| `{{erstellt_von_kontakt}}` | Kontaktdaten (E-Mail, Tel) | Text |
| `{{bemerkung}}` | Bemerkung zur Angebotsanfrage | Text |

### Lieferant-Daten

| Platzhalter | Beschreibung | Format |
|------------|-------------|--------|
| `{{lieferant_name}}` | Name des Lieferanten | Text |
| `{{lieferant_strasse}}` | Straße | Text |
| `{{lieferant_plz}}` | Postleitzahl | Text |
| `{{lieferant_ort}}` | Ort | Text |
| `{{lieferant_plz_ort}}` | PLZ und Ort kombiniert | Text |
| `{{lieferant_telefon}}` | Telefonnummer | Text |
| `{{lieferant_email}}` | E-Mail-Adresse | Text |

### Positionen

**Schleife für Positionen:**
```
{% for pos in positionen %}
| {{pos.position}} | {{pos.artikelnummer}} | {{pos.bezeichnung}} | {{pos.menge}} | {{pos.bemerkung}} |
{% endfor %}
```

**Felder pro Position:**
- `{{pos.position}}` - Positionsnummer (1, 2, 3, ...)
- `{{pos.artikelnummer}}` - Bestellnummer/Artikelnummer oder Ersatzteil-ID
- `{{pos.bezeichnung}}` - Bezeichnung des Artikels
- `{{pos.menge}}` - Menge mit Einheit (z.B. "5 Stück", "2.5 kg")
- `{{pos.bemerkung}}` - Bemerkung zur Position

**Bedingung:**
- `{{hat_positionen}}` - Boolean, ob Positionen vorhanden sind

### Firmendaten

| Platzhalter | Beschreibung | Format |
|------------|-------------|--------|
| `{{firmenname}}` | Firmenname | Text |
| `{{firmenstrasse}}` | Straße | Text |
| `{{firmenplz}}` | Postleitzahl | Text |
| `{{firmenort}}` | Ort | Text |
| `{{firmenplz_ort}}` | PLZ und Ort kombiniert | Text |
| `{{firmen_telefon}}` | Telefonnummer | Text |
| `{{firmen_website}}` | Website | Text |
| `{{firmen_email}}` | E-Mail-Adresse | Text |
| `{{firma_lieferstraße}}` | Lieferstraße (falls abweichend) | Text |
| `{{firma_lieferPLZ}}` | Liefer-PLZ | Text |
| `{{firma_lieferOrt}}` | Liefer-Ort | Text |
| `{{lieferanschrift}}` | Lieferanschrift (mehrzeilig) | Text |
| `{{footer}}` | Footer-Informationen (Geschäftsführer, UStIdNr, etc.) | Text |

---

## 3. Thema (`thema_template.docx`)

### Thema-Daten

| Platzhalter | Beschreibung | Format |
|------------|-------------|--------|
| `{{thema_id}}` | ID des Themas | Zahl |
| `{{thema_bereich}}` | Bereich | Text |
| `{{thema_gewerk}}` | Gewerk | Text |
| `{{thema_status}}` | Status | Text |
| `{{thema_status_farbe}}` | Status-Farbe (Hex) | Text (z.B. "#FF0000") |
| `{{thema_abteilung}}` | Abteilung | Text |
| `{{thema_erstellt_am}}` | Erstellungsdatum (Rohformat) | YYYY-MM-DD HH:MM:SS |
| `{{thema_erstellt_am_formatiert}}` | Erstellungsdatum formatiert | DD.MM.YYYY |

### Sichtbarkeiten

**Schleife für Sichtbarkeiten:**
```
{% for sicht in sichtbarkeiten %}
{{sicht.bezeichnung}}{% if not loop.last %}, {% endif %}
{% endfor %}
```

**Felder pro Sichtbarkeit:**
- `{{sicht.bezeichnung}}` - Name der Abteilung

**Bedingung:**
- `{{hat_sichtbarkeiten}}` - Boolean, ob Sichtbarkeiten vorhanden sind

### Bemerkungen

**Schleife für Bemerkungen:**
```
{% for bemerkung in bemerkungen %}
{{bemerkung.mitarbeiter_name}} - {{bemerkung.datum_formatiert}}
{% if bemerkung.taetigkeit %} • {{bemerkung.taetigkeit}}{% endif %}

{{bemerkung.bemerkung}}
{% endfor %}
```

**Felder pro Bemerkung:**
- `{{bemerkung.datum}}` - Datum (Rohformat) | YYYY-MM-DD HH:MM:SS
- `{{bemerkung.datum_formatiert}}` - Datum formatiert | DD.MM.YYYY HH:MM
- `{{bemerkung.mitarbeiter_vorname}}` - Vorname des Mitarbeiters
- `{{bemerkung.mitarbeiter_nachname}}` - Nachname des Mitarbeiters
- `{{bemerkung.mitarbeiter_name}}` - Vollständiger Name (Vorname Nachname)
- `{{bemerkung.taetigkeit}}` - Tätigkeit | Text
- `{{bemerkung.bemerkung}}` - Bemerkungstext | Text

**Bedingung:**
- `{{hat_bemerkungen}}` - Boolean, ob Bemerkungen vorhanden sind

### Ersatzteile

**Schleife für Ersatzteile:**
```
{% for ersatzteil in ersatzteile %}
| {{ersatzteil.datum_formatiert}} | {{ersatzteil.ersatzteil_id}} | {{ersatzteil.ersatzteil_bezeichnung}} | {{ersatzteil.typ}} | {{ersatzteil.menge_mit_einheit}} | {{ersatzteil.verwendet_von}} |
{% endfor %}
```

**Felder pro Ersatzteil:**
- `{{ersatzteil.datum}}` - Buchungsdatum (Rohformat) | YYYY-MM-DD HH:MM:SS
- `{{ersatzteil.datum_formatiert}}` - Buchungsdatum formatiert | DD.MM.YYYY
- `{{ersatzteil.ersatzteil_id}}` - ID des Ersatzteils | Zahl
- `{{ersatzteil.ersatzteil_bezeichnung}}` - Bezeichnung des Ersatzteils
- `{{ersatzteil.bestellnummer}}` - Bestellnummer des Ersatzteils
- `{{ersatzteil.typ}}` - Typ der Buchung (Ausgang, Eingang, Inventur)
- `{{ersatzteil.menge}}` - Menge (Zahl)
- `{{ersatzteil.einheit}}` - Einheit (z.B. "Stück", "kg")
- `{{ersatzteil.menge_mit_einheit}}` - Menge mit Einheit (z.B. "5 Stück")
- `{{ersatzteil.verwendet_von}}` - Name des Mitarbeiters, der es verwendet hat
- `{{ersatzteil.kostenstelle}}` - Kostenstelle
- `{{ersatzteil.preis}}` - Preis formatiert (z.B. "10.50 EUR")
- `{{ersatzteil.waehrung}}` - Währung (z.B. "EUR")

**Bedingung:**
- `{{hat_ersatzteile}}` - Boolean, ob Ersatzteile vorhanden sind

### Firmendaten

| Platzhalter | Beschreibung | Format |
|------------|-------------|--------|
| `{{firmenname}}` | Firmenname | Text |
| `{{firmenstrasse}}` | Straße | Text |
| `{{firmenplz}}` | Postleitzahl | Text |
| `{{firmenort}}` | Ort | Text |
| `{{firmenplz_ort}}` | PLZ und Ort kombiniert | Text |
| `{{firmen_telefon}}` | Telefonnummer | Text |
| `{{firmen_website}}` | Website | Text |
| `{{firmen_email}}` | E-Mail-Adresse | Text |
| `{{footer}}` | Footer-Informationen (Geschäftsführer, UStIdNr, etc.) | Text |

### Metadaten

| Platzhalter | Beschreibung | Format |
|------------|-------------|--------|
| `{{export_datum}}` | Export-Datum (Rohformat) | ISO-Format |
| `{{export_datum_formatiert}}` | Export-Datum formatiert | DD.MM.YYYY um HH:MM Uhr |

---

## Beispiele für Bedingungen

### Einfache Bedingung
```
{% if hat_positionen %}
Es gibt Positionen.
{% endif %}
```

### Bedingung mit else
```
{% if hat_bemerkungen %}
Es gibt Bemerkungen.
{% else %}
Keine Bemerkungen vorhanden.
{% endif %}
```

### Bedingung mit mehreren Bedingungen
```
{% if hat_bemerkungen and hat_ersatzteile %}
Sowohl Bemerkungen als auch Ersatzteile vorhanden.
{% endif %}
```

---

## Beispiele für Schleifen

### Einfache Schleife
```
{% for pos in positionen %}
Position {{pos.position}}: {{pos.bezeichnung}}
{% endfor %}
```

### Schleife mit Index
```
{% for bemerkung in bemerkungen %}
Bemerkung {{loop.index}}: {{bemerkung.bemerkung}}
{% endfor %}
```

### Schleife mit Trenner
```
{% for sicht in sichtbarkeiten %}
{{sicht.bezeichnung}}{% if not loop.last %}, {% endif %}
{% endfor %}
```

---

## Tabellen-Beispiele

### Bestellung - Positionen-Tabelle

```
| Pos | Artikel-Nr. | Bezeichnung | Menge | Preis | Gesamt |
|-----|-------------|-------------|-------|-------|--------|
{% for pos in positionen %}| {{pos.position}} | {{pos.artikelnummer}} | {{pos.bezeichnung}} | {{pos.menge}} | {{pos.preis}} {{pos.waehrung}} | {{pos.gesamtpreis}} {{pos.waehrung}} |{% endfor %}
|     |             |             |       |       | Gesamt: {{gesamtbetrag}} {{waehrung}} |
```

### Thema - Ersatzteile-Tabelle

```
| Datum | Ersatzteil-ID | Ersatzteil | Typ | Menge | Verwendet von |
|-------|---------------|------------|-----|-------|---------------|
{% for ersatzteil in ersatzteile %}| {{ersatzteil.datum_formatiert}} | {{ersatzteil.ersatzteil_id}} | {{ersatzteil.ersatzteil_bezeichnung}} | {{ersatzteil.typ}} | {{ersatzteil.menge_mit_einheit}} | {{ersatzteil.verwendet_von}} |{% endfor %}
```

---

## Hinweise

1. **Leere Werte:** Wenn ein Wert nicht vorhanden ist, wird ein leerer String (`''`) zurückgegeben
2. **Formatierung:** Datum-Werte sind bereits formatiert, Zahlen haben die entsprechenden Kommastellen
3. **Bilder:** Die Unterschrift bei Bestellungen wird als InlineImage eingefügt (80mm Breite)
4. **Sonderzeichen:** HTML-Sonderzeichen werden automatisch escaped
5. **Mehrzeilige Texte:** Bei mehrzeiligen Texten (z.B. Bemerkungen) werden Zeilenumbrüche beibehalten

---

## Template-Dateien

- Bestellung: `templates/reports/bestellung_template.docx`
- Angebotsanfrage: `templates/reports/angebot_template.docx`
- Thema: `templates/reports/thema_template.docx`

