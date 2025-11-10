import pandas as pd
import sqlite3
from datetime import datetime

# Konfiguration
EXCEL_FILE = 'Lagerbestandsliste.xlsx'
DATABASE_FILE = 'database_main.db'
ERSTELLER_ID = 1  # ID des Mitarbeiters, der den Import durchführt (anpassen!)

def import_ersatzteile():
    """Importiert Ersatzteile aus Excel in die Datenbank"""
    
    print("=" * 60)
    print("ERSATZTEILE IMPORT")
    print("=" * 60)
    
    # Excel-Datei einlesen
    print("\n[1/6] Lese Excel-Datei ein...")
    try:
        df_artikel = pd.read_excel(EXCEL_FILE, sheet_name='Artikelstamm')
        print(f"   OK {len(df_artikel)} Artikel gefunden")
        print(f"   Spalten: {df_artikel.columns.tolist()}")
    except Exception as e:
        print(f"   FEHLER beim Einlesen: {e}")
        return
    
    # Datenbank verbinden
    print("\n[2/6] Verbinde mit Datenbank...")
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        print("   OK Verbunden")
    except Exception as e:
        print(f"   FEHLER: {e}")
        return
    
    try:
        # ==================== ALTE DATEN LÖSCHEN ====================
        print("\n[3/6] Loesche alte Ersatzteil-Daten...")
        
        # Zähle vorhandene Ersatzteile
        anzahl_alt = cursor.execute("SELECT COUNT(*) as cnt FROM Ersatzteil WHERE Gelöscht = 0").fetchone()
        print(f"   Vorhandene Ersatzteile: {anzahl_alt['cnt']}")
        
        if anzahl_alt['cnt'] > 0:
            # Setze Gelöscht-Flag statt echtem Löschen (für Historien-Zwecke)
            cursor.execute("UPDATE Ersatzteil SET Gelöscht = 1 WHERE Gelöscht = 0")
            # Oder komplett löschen:
            cursor.execute("DELETE FROM Ersatzteil")
            conn.commit()
            print(f"   OK Alte Daten geloescht")
        else:
            print(f"   OK Keine alten Daten zum Loeschen")
        
        # ==================== IDS VALIDIEREN ====================
        print("\n[4/6] Lade Lieferanten und Kategorien zur Validierung...")
        
        # Gültige IDs sammeln
        lieferant_ids = set()
        lieferanten = cursor.execute("SELECT ID FROM Lieferant WHERE Aktiv = 1").fetchall()
        for lief in lieferanten:
            lieferant_ids.add(lief['ID'])
        print(f"   OK {len(lieferant_ids)} Lieferanten in DB")
        
        kategorie_ids = set()
        kategorien = cursor.execute("SELECT ID FROM ErsatzteilKategorie WHERE Aktiv = 1").fetchall()
        for kat in kategorien:
            kategorie_ids.add(kat['ID'])
        print(f"   OK {len(kategorie_ids)} Kategorien in DB")
        
        # ==================== ARTIKEL IMPORTIEREN ====================
        print("\n[5/6] Importiere Artikel...")
        
        erfolg = 0
        fehler = 0
        uebersprungen = 0
        fehler_details = []
        
        for idx, row in df_artikel.iterrows():
            try:
                # Pflichtfelder prüfen
                artikel_id = row.get('ArtikelID')
                bestellnummer = str(row.get('Bestellnummer', '')).strip()
                bezeichnung = str(row.get('Bezeichnung', '')).strip()
                
                if pd.isna(artikel_id):
                    fehler_details.append(f"Zeile {idx+2}: Fehlende Artikel-ID")
                    uebersprungen += 1
                    continue
                
                if not bestellnummer or bestellnummer == 'nan':
                    fehler_details.append(f"Zeile {idx+2}: Fehlende Bestellnummer")
                    uebersprungen += 1
                    continue
                
                if not bezeichnung or bezeichnung == 'nan':
                    fehler_details.append(f"Zeile {idx+2}: Fehlende Bezeichnung")
                    uebersprungen += 1
                    continue
                
                # Prüfe ob Artikel bereits existiert (nach Bestellnummer)
                existing = cursor.execute(
                    "SELECT ID FROM Ersatzteil WHERE Bestellnummer = ?", 
                    (bestellnummer,)
                ).fetchone()
                
                if existing:
                    print(f"   >> {bestellnummer} - {bezeichnung} (bereits vorhanden)")
                    uebersprungen += 1
                    continue
                
                # Lieferanten-ID direkt aus Excel
                lieferant_id = None
                if pd.notna(row.get('LieferantID')):
                    try:
                        lieferant_id = int(row.get('LieferantID'))
                        if lieferant_id not in lieferant_ids:
                            print(f"   WARNUNG Zeile {idx+2}: LieferantID {lieferant_id} nicht in DB gefunden")
                            lieferant_id = None
                    except (ValueError, TypeError):
                        pass
                
                # Kategorie-ID direkt aus Excel
                kategorie_id = None
                if pd.notna(row.get('KategorieID')):
                    try:
                        kategorie_id = int(row.get('KategorieID'))
                        if kategorie_id not in kategorie_ids:
                            print(f"   WARNUNG Zeile {idx+2}: KategorieID {kategorie_id} nicht in DB gefunden")
                            kategorie_id = None
                    except (ValueError, TypeError):
                        pass
                
                # Artikel einfügen mit expliziter ID (wichtig für Beschriftungen!)
                cursor.execute("""
                    INSERT INTO Ersatzteil (
                        ID, Bestellnummer, Bezeichnung, Beschreibung,
                        KategorieID, Hersteller, LieferantID, 
                        Preis, Waehrung, Lagerort,
                        Mindestbestand, AktuellerBestand, Einheit,
                        EndOfLife, Kennzeichen, ArtikelnummerHersteller,
                        NachfolgeartikelID, Aktiv, Gelöscht, ErstelltVonID
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?)
                """, (
                    int(artikel_id),
                    bestellnummer,
                    bezeichnung,
                    None,  # Beschreibung (nicht in Excel)
                    kategorie_id,
                    None,  # Hersteller (nicht in Excel)
                    lieferant_id,
                    float(row.get('Preis', 0)) if pd.notna(row.get('Preis')) else None,
                    'EUR',  # Waehrung (Standard)
                    None,  # Lagerort (nicht in Excel)
                    0,  # Mindestbestand (nicht in Excel)
                    int(row.get('Bestand', 0)) if pd.notna(row.get('Bestand')) else 0,
                    str(row.get('Einheit', 'Stueck')).strip() if pd.notna(row.get('Einheit')) else 'Stueck',
                    0,  # EndOfLife (nicht in Excel)
                    None,  # Kennzeichen (nicht in Excel)
                    str(row.get('Artikelnummer Hersteller', '')).strip() if pd.notna(row.get('Artikelnummer Hersteller')) else None,
                    int(row.get('NachfolgeartikelID', 0)) if pd.notna(row.get('NachfolgeartikelID')) and row.get('NachfolgeartikelID') != 0 else None,
                    ERSTELLER_ID
                ))
                
                erfolg += 1
                if erfolg % 10 == 0:  # Fortschritt alle 10 Artikel
                    print(f"   ... {erfolg} Artikel importiert")
                
            except sqlite3.IntegrityError as e:
                fehler += 1
                fehler_details.append(f"Zeile {idx+2} (ID {artikel_id}): {e}")
            except Exception as e:
                fehler += 1
                fehler_details.append(f"Zeile {idx+2}: {e}")
        
        conn.commit()
        
        # ==================== ZUSAMMENFASSUNG ====================
        print("\n[6/6] Import abgeschlossen!")
        print("\n" + "=" * 60)
        print("IMPORT ABGESCHLOSSEN")
        print("=" * 60)
        print(f"[OK] Erfolgreich importiert:  {erfolg} Artikel")
        print(f"[>>] Uebersprungen:           {uebersprungen} Artikel")
        print(f"[XX] Fehler:                  {fehler} Artikel")
        print("=" * 60)
        
        # Fehlerdetails anzeigen
        if fehler_details:
            print("\nFEHLER-DETAILS:")
            for detail in fehler_details[:20]:  # Maximal 20 Fehler anzeigen
                print(f"  - {detail}")
            if len(fehler_details) > 20:
                print(f"  ... und {len(fehler_details) - 20} weitere Fehler")
        
        # Finale Statistik aus DB
        print("\nDATENBANK-STATISTIK:")
        anzahl = cursor.execute("SELECT COUNT(*) as cnt FROM Ersatzteil WHERE Gelöscht = 0").fetchone()
        print(f"  Gesamt Ersatzteile in DB: {anzahl['cnt']}")
        
        # Statistik mit Lieferanten/Kategorien
        anzahl_mit_lieferant = cursor.execute("SELECT COUNT(*) as cnt FROM Ersatzteil WHERE Gelöscht = 0 AND LieferantID IS NOT NULL").fetchone()
        anzahl_mit_kategorie = cursor.execute("SELECT COUNT(*) as cnt FROM Ersatzteil WHERE Gelöscht = 0 AND KategorieID IS NOT NULL").fetchone()
        print(f"  Mit Lieferant:              {anzahl_mit_lieferant['cnt']}")
        print(f"  Mit Kategorie:              {anzahl_mit_kategorie['cnt']}")
        
    except Exception as e:
        print(f"\n[XX] KRITISCHER FEHLER: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()
        print("\nDatenbankverbindung geschlossen.")

if __name__ == '__main__':
    import_ersatzteile()

