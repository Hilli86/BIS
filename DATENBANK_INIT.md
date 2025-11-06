# Datenbank-Initialisierung für BIS

## Überblick

Das Script `init_database.py` erstellt eine neue SQLite-Datenbank für das BIS (Betriebsinformationssystem) mit allen benötigten Tabellen und einem Admin-Benutzer.

## Voraussetzungen

- Python 3.x
- Python-Abhängigkeiten installiert:
  ```bash
  py -m pip install -r requirements.txt
  ```

## Verwendung

### Datenbank initialisieren

Führen Sie im Projektverzeichnis aus:

```bash
py init_database.py
```

Das Script:
1. Prüft, ob bereits eine Datenbank existiert (mit Rückfrage zum Überschreiben)
2. Erstellt alle benötigten Tabellen
3. Legt die BIS-Admin Abteilung an
4. Erstellt den BIS-Admin Benutzer

## Standard-Login nach Initialisierung

Nach erfolgreicher Initialisierung können Sie sich mit folgenden Daten anmelden:

- **Personalnummer:** `99999`
- **Passwort:** `a`

## Erstellte Tabellen

Das Script erstellt folgende Tabellen:

1. **Mitarbeiter** - Benutzer des Systems
2. **Abteilung** - Hierarchische Abteilungsstruktur
3. **MitarbeiterAbteilung** - Zusätzliche Abteilungszuordnungen
4. **Bereich** - Bereiche für Gewerke
5. **Gewerke** - Gewerke/Kategorien
6. **Status** - Status für Themen
7. **Taetigkeit** - Tätigkeitsarten
8. **SchichtbuchThema** - Schichtbuch-Themen
9. **SchichtbuchBemerkungen** - Bemerkungen zu Themen
10. **SchichtbuchThemaSichtbarkeit** - Sichtbarkeitssteuerung für Themen

Alle Tabellen werden mit den entsprechenden Indizes für optimale Performance erstellt.

## Hinweise

- Die Datenbank wird standardmäßig als `database_main.db` im Projektverzeichnis erstellt
- Bei erneutem Ausführen wird gefragt, ob die existierende Datenbank überschrieben werden soll
- Das Admin-Passwort sollte nach dem ersten Login geändert werden (sobald diese Funktion implementiert ist)

## Problembehandlung

### Fehler: Modul 'werkzeug' nicht gefunden

Lösung:
```bash
py -m pip install -r requirements.txt
```

### Datenbank ist gesperrt

Lösung:
- Stellen Sie sicher, dass keine andere Anwendung die Datenbank verwendet
- Schließen Sie alle laufenden Python-Prozesse
- Starten Sie das Initialisierungsskript erneut

