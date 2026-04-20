"""
SQLAlchemy-Core-Metadaten fuer das BIS-Schema.

Zentrale ``MetaData``-Instanz; Alembic (``alembic/env.py``) bindet sie als
``target_metadata``. Die Tabellen-, Spalten-, Index- und Constraint-Namen
entsprechen dem aktuellen SQLite-Schema aus
``utils/database_schema_init.py`` 1:1, damit:

- eine ``autogenerate``-Baseline gegen die bestehende Datenbank keine
  Ueberraschungen produziert und
- ``alembic upgrade head`` auf einer frischen SQLite- oder Postgres-Instanz
  dasselbe logische Schema erzeugt.

Phase 1: Nur deklarative Tabellen-/Index-Definitionen. Keine Queries, keine
Business-Logik.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    text,
)

# Einheitliche Namenskonvention fuer Constraints/Indizes (hilft Alembic, in
# spaeteren Migrationen Namen deterministisch zu vergeben).
NAMING_CONVENTION = {
    'ix': 'ix_%(table_name)s_%(column_0_N_name)s',
    'uq': 'uq_%(table_name)s_%(column_0_N_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Kleine Helfer, um sich wiederholende Column-Muster kompakt zu halten.
def _pk():
    return Column('ID', Integer, primary_key=True, autoincrement=True)


def _pk_lower():
    return Column('id', Integer, primary_key=True, autoincrement=True)


def _aktiv(default: int = 1, not_null: bool = True):
    return Column(
        'Aktiv',
        Integer,
        nullable=not not_null,
        server_default=text(str(default)),
    )


def _ts_now(name: str = 'ErstelltAm', nullable: bool = True):
    return Column(
        name,
        DateTime,
        nullable=nullable,
        server_default=text('CURRENT_TIMESTAMP'),
    )


# ---------------------------------------------------------------------------
# Stammdaten
# ---------------------------------------------------------------------------

Mitarbeiter = Table(
    'Mitarbeiter', metadata,
    _pk(),
    Column('Personalnummer', Text, nullable=False, unique=True),
    Column('Vorname', Text),
    Column('Nachname', Text, nullable=False),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Column('Passwort', Text, nullable=False),
    Column('PrimaerAbteilungID', Integer, ForeignKey('Abteilung.ID')),
    Column('Email', Text),
    Column('Handynummer', Text),
    Column('StartseiteNachLoginEndpunkt', Text),
    Column('PasswortWechselErforderlich', Integer, nullable=False, server_default=text('0')),
    Index('idx_mitarbeiter_aktiv', 'Aktiv'),
    Index('idx_mitarbeiter_personalnummer', 'Personalnummer'),
)

Abteilung = Table(
    'Abteilung', metadata,
    _pk(),
    Column('Bezeichnung', Text, nullable=False),
    Column('ParentAbteilungID', Integer, ForeignKey('Abteilung.ID')),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Column('Sortierung', Integer, server_default=text('0')),
    Index('idx_abteilung_parent', 'ParentAbteilungID'),
    Index('idx_abteilung_aktiv', 'Aktiv'),
)

MitarbeiterAbteilung = Table(
    'MitarbeiterAbteilung', metadata,
    _pk(),
    Column('MitarbeiterID', Integer, ForeignKey('Mitarbeiter.ID', ondelete='CASCADE'), nullable=False),
    Column('AbteilungID', Integer, ForeignKey('Abteilung.ID', ondelete='CASCADE'), nullable=False),
    UniqueConstraint('MitarbeiterID', 'AbteilungID'),
    Index('idx_mitarbeiter_abteilung_ma', 'MitarbeiterID'),
    Index('idx_mitarbeiter_abteilung_abt', 'AbteilungID'),
)

Bereich = Table(
    'Bereich', metadata,
    _pk(),
    Column('Bezeichnung', Text, nullable=False),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Index('idx_bereich_aktiv', 'Aktiv'),
)

Gewerke = Table(
    'Gewerke', metadata,
    _pk(),
    Column('Bezeichnung', Text, nullable=False),
    Column('BereichID', Integer, ForeignKey('Bereich.ID'), nullable=False),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Index('idx_gewerke_bereich', 'BereichID'),
    Index('idx_gewerke_aktiv', 'Aktiv'),
)

Status = Table(
    'Status', metadata,
    _pk(),
    Column('Bezeichnung', Text, nullable=False),
    Column('Farbe', Text),
    Column('Sortierung', Integer, server_default=text('0')),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Index('idx_status_aktiv', 'Aktiv'),
)

Taetigkeit = Table(
    'Taetigkeit', metadata,
    _pk(),
    Column('Bezeichnung', Text, nullable=False),
    Column('Sortierung', Integer, server_default=text('0')),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Index('idx_taetigkeit_aktiv', 'Aktiv'),
)


# ---------------------------------------------------------------------------
# Schichtbuch
# ---------------------------------------------------------------------------

SchichtbuchThema = Table(
    'SchichtbuchThema', metadata,
    _pk(),
    Column('GewerkID', Integer, ForeignKey('Gewerke.ID'), nullable=False),
    Column('StatusID', Integer, ForeignKey('Status.ID'), nullable=False),
    Column('ErstellerAbteilungID', Integer, ForeignKey('Abteilung.ID')),
    Column('Gel\u00f6scht', Integer, nullable=False, server_default=text('0')),
    _ts_now('ErstelltAm'),
    Index('idx_thema_gewerk', 'GewerkID'),
    Index('idx_thema_status', 'StatusID'),
    Index('idx_thema_abteilung', 'ErstellerAbteilungID'),
    Index('idx_thema_geloescht', 'Gel\u00f6scht'),
)

SchichtbuchBemerkungen = Table(
    'SchichtbuchBemerkungen', metadata,
    _pk(),
    Column('ThemaID', Integer, ForeignKey('SchichtbuchThema.ID', ondelete='CASCADE'), nullable=False),
    Column('MitarbeiterID', Integer, ForeignKey('Mitarbeiter.ID'), nullable=False),
    _ts_now('Datum'),
    Column('TaetigkeitID', Integer, ForeignKey('Taetigkeit.ID')),
    Column('Bemerkung', Text),
    Column('Gel\u00f6scht', Integer, nullable=False, server_default=text('0')),
    Index('idx_bemerkung_thema', 'ThemaID'),
    Index('idx_bemerkung_mitarbeiter', 'MitarbeiterID'),
    Index('idx_bemerkung_geloescht', 'Gel\u00f6scht'),
)

SchichtbuchThemaSichtbarkeit = Table(
    'SchichtbuchThemaSichtbarkeit', metadata,
    _pk(),
    Column('ThemaID', Integer, ForeignKey('SchichtbuchThema.ID', ondelete='CASCADE'), nullable=False),
    Column('AbteilungID', Integer, ForeignKey('Abteilung.ID', ondelete='CASCADE'), nullable=False),
    _ts_now('ErstelltAm'),
    UniqueConstraint('ThemaID', 'AbteilungID'),
    Index('idx_sichtbarkeit_thema', 'ThemaID'),
    Index('idx_sichtbarkeit_abteilung', 'AbteilungID'),
)

SchichtbuchThemaGewerk = Table(
    'SchichtbuchThemaGewerk', metadata,
    _pk(),
    Column('ThemaID', Integer, ForeignKey('SchichtbuchThema.ID', ondelete='CASCADE'), nullable=False),
    Column('GewerkID', Integer, ForeignKey('Gewerke.ID', ondelete='CASCADE'), nullable=False),
    _ts_now('ErstelltAm'),
    UniqueConstraint('ThemaID', 'GewerkID'),
    Index('idx_thema_gewerk_thema', 'ThemaID'),
    Index('idx_thema_gewerk_gewerk', 'GewerkID'),
)

Aufgabenliste = Table(
    'Aufgabenliste', metadata,
    _pk(),
    Column('Bezeichnung', Text, nullable=False),
    Column('Beschreibung', Text),
    Column('ErstellerMitarbeiterID', Integer, ForeignKey('Mitarbeiter.ID'), nullable=False),
    _ts_now('ErstelltAm'),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Index('idx_aufgabenliste_ersteller', 'ErstellerMitarbeiterID'),
    Index('idx_aufgabenliste_aktiv', 'Aktiv'),
)

AufgabenlisteSichtbarkeitAbteilung = Table(
    'AufgabenlisteSichtbarkeitAbteilung', metadata,
    _pk(),
    Column('AufgabenlisteID', Integer, ForeignKey('Aufgabenliste.ID', ondelete='CASCADE'), nullable=False),
    Column('AbteilungID', Integer, ForeignKey('Abteilung.ID', ondelete='CASCADE'), nullable=False),
    UniqueConstraint('AufgabenlisteID', 'AbteilungID'),
    Index('idx_aufgsicht_abt_liste', 'AufgabenlisteID'),
    Index('idx_aufgsicht_abt_abt', 'AbteilungID'),
)

AufgabenlisteSichtbarkeitMitarbeiter = Table(
    'AufgabenlisteSichtbarkeitMitarbeiter', metadata,
    _pk(),
    Column('AufgabenlisteID', Integer, ForeignKey('Aufgabenliste.ID', ondelete='CASCADE'), nullable=False),
    Column('MitarbeiterID', Integer, ForeignKey('Mitarbeiter.ID', ondelete='CASCADE'), nullable=False),
    UniqueConstraint('AufgabenlisteID', 'MitarbeiterID'),
    Index('idx_aufgsicht_ma_liste', 'AufgabenlisteID'),
    Index('idx_aufgsicht_ma_ma', 'MitarbeiterID'),
)

AufgabenlisteThema = Table(
    'AufgabenlisteThema', metadata,
    _pk(),
    Column('AufgabenlisteID', Integer, ForeignKey('Aufgabenliste.ID', ondelete='CASCADE'), nullable=False),
    Column('ThemaID', Integer, ForeignKey('SchichtbuchThema.ID', ondelete='CASCADE'), nullable=False),
    Column('Sortierung', Integer, nullable=False, server_default=text('0')),
    _ts_now('HinzugefuegtAm'),
    Column('HinzugefuegtVonMitarbeiterID', Integer, ForeignKey('Mitarbeiter.ID')),
    UniqueConstraint('AufgabenlisteID', 'ThemaID'),
    Index('idx_aufgthema_liste', 'AufgabenlisteID'),
    Index('idx_aufgthema_thema', 'ThemaID'),
)


# ---------------------------------------------------------------------------
# Benachrichtigungen
# ---------------------------------------------------------------------------

Benachrichtigung = Table(
    'Benachrichtigung', metadata,
    _pk(),
    Column('MitarbeiterID', Integer, ForeignKey('Mitarbeiter.ID', ondelete='CASCADE'), nullable=False),
    Column('ThemaID', Integer, ForeignKey('SchichtbuchThema.ID', ondelete='CASCADE'), nullable=False),
    Column('BemerkungID', Integer, ForeignKey('SchichtbuchBemerkungen.ID', ondelete='CASCADE')),
    Column('Typ', Text, nullable=False),
    Column('Titel', Text, nullable=False),
    Column('Nachricht', Text, nullable=False),
    Column('Gelesen', Integer, nullable=False, server_default=text('0')),
    _ts_now('ErstelltAm'),
    Column('Modul', Text),
    Column('Aktion', Text),
    Column('AbteilungID', Integer, ForeignKey('Abteilung.ID')),
    Column('Zusatzdaten', Text),
    Index('idx_benachrichtigung_mitarbeiter', 'MitarbeiterID'),
    Index('idx_benachrichtigung_thema', 'ThemaID'),
    Index('idx_benachrichtigung_gelesen', 'Gelesen'),
    Index('idx_benachrichtigung_erstellt', 'ErstelltAm'),
    Index('idx_benachrichtigung_modul', 'Modul'),
    Index('idx_benachrichtigung_aktion', 'Aktion'),
    Index('idx_benachrichtigung_abteilung', 'AbteilungID'),
)

BenachrichtigungEinstellung = Table(
    'BenachrichtigungEinstellung', metadata,
    _pk(),
    Column('MitarbeiterID', Integer, ForeignKey('Mitarbeiter.ID', ondelete='CASCADE'), nullable=False),
    Column('Modul', Text, nullable=False),
    Column('Aktion', Text, nullable=False),
    Column('AbteilungID', Integer, ForeignKey('Abteilung.ID', ondelete='CASCADE')),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    UniqueConstraint('MitarbeiterID', 'Modul', 'Aktion', 'AbteilungID'),
    Index('idx_benachrichtigung_einstellung_mitarbeiter', 'MitarbeiterID'),
    Index('idx_benachrichtigung_einstellung_modul', 'Modul'),
    Index('idx_benachrichtigung_einstellung_aktion', 'Aktion'),
    Index('idx_benachrichtigung_einstellung_abteilung', 'AbteilungID'),
)

BenachrichtigungKanal = Table(
    'BenachrichtigungKanal', metadata,
    _pk(),
    Column('MitarbeiterID', Integer, ForeignKey('Mitarbeiter.ID', ondelete='CASCADE'), nullable=False),
    Column('KanalTyp', Text, nullable=False),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Column('Konfiguration', Text),
    UniqueConstraint('MitarbeiterID', 'KanalTyp'),
    Index('idx_benachrichtigung_kanal_mitarbeiter', 'MitarbeiterID'),
    Index('idx_benachrichtigung_kanal_typ', 'KanalTyp'),
    Index('idx_benachrichtigung_kanal_aktiv', 'Aktiv'),
)

BenachrichtigungVersand = Table(
    'BenachrichtigungVersand', metadata,
    _pk(),
    Column('BenachrichtigungID', Integer, ForeignKey('Benachrichtigung.ID', ondelete='CASCADE'), nullable=False),
    Column('KanalTyp', Text, nullable=False),
    Column('Status', Text, nullable=False, server_default=text("'pending'")),
    Column('VersandAm', DateTime),
    Column('Fehlermeldung', Text),
    Index('idx_benachrichtigung_versand_benachrichtigung', 'BenachrichtigungID'),
    Index('idx_benachrichtigung_versand_kanal', 'KanalTyp'),
    Index('idx_benachrichtigung_versand_status', 'Status'),
    Index('idx_benachrichtigung_versand_versand_am', 'VersandAm'),
)


# ---------------------------------------------------------------------------
# Ersatzteile / Lager
# ---------------------------------------------------------------------------

ErsatzteilKategorie = Table(
    'ErsatzteilKategorie', metadata,
    _pk(),
    Column('Bezeichnung', Text, nullable=False),
    Column('Beschreibung', Text),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Column('Sortierung', Integer, server_default=text('0')),
    Index('idx_ersatzteil_kategorie_aktiv', 'Aktiv'),
    Index('idx_ersatzteil_kategorie_sortierung', 'Sortierung'),
)

Kostenstelle = Table(
    'Kostenstelle', metadata,
    _pk(),
    Column('Bezeichnung', Text, nullable=False),
    Column('Beschreibung', Text),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Column('Sortierung', Integer, server_default=text('0')),
    Index('idx_kostenstelle_aktiv', 'Aktiv'),
    Index('idx_kostenstelle_sortierung', 'Sortierung'),
)

Lieferant = Table(
    'Lieferant', metadata,
    _pk(),
    Column('Name', Text, nullable=False),
    Column('Kontaktperson', Text),
    Column('Telefon', Text),
    Column('Email', Text),
    Column('Strasse', Text),
    Column('PLZ', Text),
    Column('Ort', Text),
    Column('Website', Text),
    Column('CsvExportReihenfolge', Text),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Column('Gel\u00f6scht', Integer, nullable=False, server_default=text('0')),
    Index('idx_lieferant_aktiv', 'Aktiv'),
    Index('idx_lieferant_geloescht', 'Gel\u00f6scht'),
)

Lagerort = Table(
    'Lagerort', metadata,
    _pk(),
    Column('Bezeichnung', Text, nullable=False),
    Column('Beschreibung', Text),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Column('Sortierung', Integer, server_default=text('0')),
    Index('idx_lagerort_aktiv', 'Aktiv'),
    Index('idx_lagerort_sortierung', 'Sortierung'),
)

Lagerplatz = Table(
    'Lagerplatz', metadata,
    _pk(),
    Column('Bezeichnung', Text, nullable=False),
    Column('Beschreibung', Text),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Column('Sortierung', Integer, server_default=text('0')),
    Index('idx_lagerplatz_aktiv', 'Aktiv'),
    Index('idx_lagerplatz_sortierung', 'Sortierung'),
)

Ersatzteil = Table(
    'Ersatzteil', metadata,
    _pk(),
    Column('Bestellnummer', Text, nullable=False, unique=True),
    Column('Bezeichnung', Text, nullable=False),
    Column('Beschreibung', Text),
    Column('KategorieID', Integer, ForeignKey('ErsatzteilKategorie.ID')),
    Column('Hersteller', Text),
    Column('LieferantID', Integer, ForeignKey('Lieferant.ID')),
    Column('Preis', Float),
    Column('Waehrung', Text, server_default=text("'EUR'")),
    Column('Lagerort', Text),
    Column('LagerortID', Integer, ForeignKey('Lagerort.ID')),
    Column('LagerplatzID', Integer, ForeignKey('Lagerplatz.ID')),
    Column('Mindestbestand', Integer, server_default=text('0')),
    Column('AktuellerBestand', Integer, server_default=text('0')),
    Column('Einheit', Text, server_default=text("'St\u00fcck'")),
    Column('EndOfLife', Integer, nullable=False, server_default=text('0')),
    Column('NachfolgeartikelID', Integer, ForeignKey('Ersatzteil.ID')),
    Column('Kennzeichen', Text),
    Column('ArtikelnummerHersteller', Text),
    Column('Link', Text),
    Column('Preisstand', DateTime),
    Column('ArtikelfotoPfad', Text),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Column('Gel\u00f6scht', Integer, nullable=False, server_default=text('0')),
    _ts_now('ErstelltAm'),
    Column('ErstelltVonID', Integer, ForeignKey('Mitarbeiter.ID')),
    Index('idx_ersatzteil_bestellnummer', 'Bestellnummer'),
    Index('idx_ersatzteil_kategorie', 'KategorieID'),
    Index('idx_ersatzteil_lieferant', 'LieferantID'),
    Index('idx_ersatzteil_aktiv', 'Aktiv'),
    Index('idx_ersatzteil_geloescht', 'Gel\u00f6scht'),
    Index('idx_ersatzteil_bestand', 'AktuellerBestand'),
    Index('idx_ersatzteil_lagerort', 'LagerortID'),
    Index('idx_ersatzteil_lagerplatz', 'LagerplatzID'),
    Index('idx_ersatzteil_nachfolgeartikel', 'NachfolgeartikelID'),
    Index('idx_ersatzteil_kennzeichen', 'Kennzeichen'),
    Index('idx_ersatzteil_artikelnummer_hersteller', 'ArtikelnummerHersteller'),
)

ErsatzteilBild = Table(
    'ErsatzteilBild', metadata,
    _pk(),
    Column('ErsatzteilID', Integer, ForeignKey('Ersatzteil.ID', ondelete='CASCADE'), nullable=False),
    Column('Dateiname', Text, nullable=False),
    Column('Dateipfad', Text, nullable=False),
    Column('Beschreibung', Text),
    _ts_now('ErstelltAm'),
    Index('idx_ersatzteil_bild_ersatzteil', 'ErsatzteilID'),
)

ErsatzteilDokument = Table(
    'ErsatzteilDokument', metadata,
    _pk(),
    Column('ErsatzteilID', Integer, ForeignKey('Ersatzteil.ID', ondelete='CASCADE'), nullable=False),
    Column('Dateiname', Text, nullable=False),
    Column('Dateipfad', Text, nullable=False),
    Column('Typ', Text),
    Column('Beschreibung', Text),
    _ts_now('ErstelltAm'),
    Index('idx_ersatzteil_dokument_ersatzteil', 'ErsatzteilID'),
)

Lagerbuchung = Table(
    'Lagerbuchung', metadata,
    _pk(),
    Column('ErsatzteilID', Integer, ForeignKey('Ersatzteil.ID'), nullable=False),
    Column('Typ', Text, nullable=False),
    Column('Menge', Integer, nullable=False),
    Column('Grund', Text),
    Column('ThemaID', Integer, ForeignKey('SchichtbuchThema.ID')),
    Column('KostenstelleID', Integer, ForeignKey('Kostenstelle.ID')),
    Column('WartungsdurchfuehrungID', Integer),
    Column('BestellungID', Integer),
    Column('VerwendetVonID', Integer, ForeignKey('Mitarbeiter.ID'), nullable=False),
    _ts_now('Buchungsdatum'),
    Column('Bemerkung', Text),
    Column('Preis', Float),
    Column('Waehrung', Text),
    _ts_now('ErstelltAm'),
    Index('idx_lagerbuchung_ersatzteil', 'ErsatzteilID'),
    Index('idx_lagerbuchung_thema', 'ThemaID'),
    Index('idx_lagerbuchung_kostenstelle', 'KostenstelleID'),
    Index('idx_lagerbuchung_verwendet_von', 'VerwendetVonID'),
    Index('idx_lagerbuchung_buchungsdatum', 'Buchungsdatum'),
    Index('idx_lagerbuchung_bestellung', 'BestellungID'),
    Index('idx_lagerbuchung_wartungsdurchfuehrung', 'WartungsdurchfuehrungID'),
)

ErsatzteilAbteilungZugriff = Table(
    'ErsatzteilAbteilungZugriff', metadata,
    _pk(),
    Column('ErsatzteilID', Integer, ForeignKey('Ersatzteil.ID', ondelete='CASCADE'), nullable=False),
    Column('AbteilungID', Integer, ForeignKey('Abteilung.ID', ondelete='CASCADE'), nullable=False),
    UniqueConstraint('ErsatzteilID', 'AbteilungID'),
    Index('idx_ersatzteil_abteilung_ersatzteil', 'ErsatzteilID'),
    Index('idx_ersatzteil_abteilung_abteilung', 'AbteilungID'),
)


# ---------------------------------------------------------------------------
# Wartungen
# ---------------------------------------------------------------------------

Wartung = Table(
    'Wartung', metadata,
    _pk(),
    Column('GewerkID', Integer, ForeignKey('Gewerke.ID'), nullable=False),
    Column('Bezeichnung', Text, nullable=False),
    Column('Beschreibung', Text),
    Column('DokuSharepointOrdnerUrl', Text),
    Column('ErstelltVonID', Integer, ForeignKey('Mitarbeiter.ID'), nullable=False),
    _ts_now('ErstelltAm'),
    Column('GeaendertAm', DateTime),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Index('idx_wartung_gewerk', 'GewerkID'),
    Index('idx_wartung_erstellt_von', 'ErstelltVonID'),
    Index('idx_wartung_aktiv', 'Aktiv'),
)

WartungAbteilungZugriff = Table(
    'WartungAbteilungZugriff', metadata,
    _pk(),
    Column('WartungID', Integer, ForeignKey('Wartung.ID', ondelete='CASCADE'), nullable=False),
    Column('AbteilungID', Integer, ForeignKey('Abteilung.ID', ondelete='CASCADE'), nullable=False),
    UniqueConstraint('WartungID', 'AbteilungID'),
    Index('idx_wartung_abteilung_wartung', 'WartungID'),
    Index('idx_wartung_abteilung_abteilung', 'AbteilungID'),
)

Fremdfirma = Table(
    'Fremdfirma', metadata,
    _pk(),
    Column('Firmenname', Text, nullable=False),
    Column('Adresse', Text),
    Column('Taetigkeitsbereich', Text),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Index('idx_fremdfirma_aktiv', 'Aktiv'),
)

Wartungsplan = Table(
    'Wartungsplan', metadata,
    _pk(),
    Column('WartungID', Integer, ForeignKey('Wartung.ID', ondelete='CASCADE'), nullable=False),
    Column('IntervallEinheit', Text, nullable=False),
    Column('IntervallAnzahl', Integer, nullable=False, server_default=text('1')),
    Column('NaechsteFaelligkeit', Date),
    Column('HatFestesIntervall', Integer, nullable=False, server_default=text('0')),
    Column('ErinnerungTageVor', Integer),
    Column('TerminVereinbart', Integer, nullable=False, server_default=text('0')),
    Column('TerminVereinbartDatum', Date),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    _ts_now('ErstelltAm'),
    Index('idx_wartungsplan_wartung', 'WartungID'),
    Index('idx_wartungsplan_aktiv', 'Aktiv'),
)

Wartungsdurchfuehrung = Table(
    'Wartungsdurchfuehrung', metadata,
    _pk(),
    Column('WartungsplanID', Integer, ForeignKey('Wartungsplan.ID', ondelete='CASCADE'), nullable=False),
    Column('DurchgefuehrtAm', DateTime, nullable=False),
    Column('Bemerkung', Text),
    Column('ProtokolliertVonID', Integer, ForeignKey('Mitarbeiter.ID')),
    Column('AngebotsanfrageID', Integer),
    Column('AngebotsKostenBetrag', Float),
    Column('AngebotsKostenWaehrung', Text),
    _ts_now('ErstelltAm'),
    Index('idx_wartungsdurchfuehrung_plan', 'WartungsplanID'),
    Index('idx_wartungsdurchfuehrung_datum', 'DurchgefuehrtAm'),
    Index('idx_wartungsdurchfuehrung_angebot', 'AngebotsanfrageID'),
)

WartungsdurchfuehrungMitarbeiter = Table(
    'WartungsdurchfuehrungMitarbeiter', metadata,
    _pk(),
    Column('WartungsdurchfuehrungID', Integer, ForeignKey('Wartungsdurchfuehrung.ID', ondelete='CASCADE'), nullable=False),
    Column('MitarbeiterID', Integer, ForeignKey('Mitarbeiter.ID'), nullable=False),
    UniqueConstraint('WartungsdurchfuehrungID', 'MitarbeiterID'),
    Index('idx_wd_ma_durchfuehrung', 'WartungsdurchfuehrungID'),
    Index('idx_wd_ma_mitarbeiter', 'MitarbeiterID'),
)

WartungsdurchfuehrungFremdfirma = Table(
    'WartungsdurchfuehrungFremdfirma', metadata,
    _pk(),
    Column('WartungsdurchfuehrungID', Integer, ForeignKey('Wartungsdurchfuehrung.ID', ondelete='CASCADE'), nullable=False),
    Column('FremdfirmaID', Integer, ForeignKey('Fremdfirma.ID'), nullable=False),
    Column('Techniker', Text, nullable=False),
    Column('Telefon', Text),
    Index('idx_wd_ff_durchfuehrung', 'WartungsdurchfuehrungID'),
    Index('idx_wd_ff_fremdfirma', 'FremdfirmaID'),
)


# ---------------------------------------------------------------------------
# Dateien / Firmendaten / LoginLog
# ---------------------------------------------------------------------------

Datei = Table(
    'Datei', metadata,
    _pk(),
    Column('BereichTyp', Text, nullable=False),
    Column('BereichID', Integer, nullable=False),
    Column('Dateiname', Text, nullable=False),
    Column('Dateipfad', Text, nullable=False),
    Column('Beschreibung', Text),
    Column('Typ', Text),
    _ts_now('ErstelltAm'),
    Column('ErstelltVonID', Integer, ForeignKey('Mitarbeiter.ID')),
    Index('idx_datei_bereich', 'BereichTyp', 'BereichID'),
    Index('idx_datei_typ', 'Typ'),
    Index('idx_datei_erstellt_von', 'ErstelltVonID'),
)

LoginLog = Table(
    'LoginLog', metadata,
    _pk(),
    Column('Personalnummer', Text),
    Column('MitarbeiterID', Integer, ForeignKey('Mitarbeiter.ID')),
    Column('Erfolgreich', Integer, nullable=False, server_default=text('1')),
    Column('IPAdresse', Text),
    Column('UserAgent', Text),
    Column('Fehlermeldung', Text),
    _ts_now('Zeitpunkt'),
    Index('idx_loginlog_mitarbeiter', 'MitarbeiterID'),
    Index('idx_loginlog_zeitpunkt', 'Zeitpunkt'),
    Index('idx_loginlog_erfolgreich', 'Erfolgreich'),
    Index('idx_loginlog_personalnummer', 'Personalnummer'),
)

Firmendaten = Table(
    'Firmendaten', metadata,
    _pk(),
    Column('Firmenname', Text, nullable=False),
    Column('Strasse', Text),
    Column('PLZ', Text),
    Column('Ort', Text),
    Column('LieferStrasse', Text),
    Column('LieferPLZ', Text),
    Column('LieferOrt', Text),
    Column('Telefon', Text),
    Column('Fax', Text),
    Column('Email', Text),
    Column('Website', Text),
    Column('Steuernummer', Text),
    Column('UStIdNr', Text),
    Column('Geschaeftsfuehrer', Text),
    Column('LogoPfad', Text),
    Column('BankName', Text),
    Column('IBAN', Text),
    Column('BIC', Text),
    _ts_now('ErstelltAm'),
    _ts_now('GeaendertAm'),
)


# ---------------------------------------------------------------------------
# Angebote / Bestellungen
# ---------------------------------------------------------------------------

Angebotsanfrage = Table(
    'Angebotsanfrage', metadata,
    _pk(),
    Column('LieferantID', Integer, ForeignKey('Lieferant.ID'), nullable=False),
    Column('ErstelltVonID', Integer, ForeignKey('Mitarbeiter.ID'), nullable=False),
    Column('ErstellerAbteilungID', Integer, ForeignKey('Abteilung.ID')),
    Column('Status', Text, nullable=False, server_default=text("'Offen'")),
    _ts_now('ErstelltAm'),
    Column('VersendetAm', DateTime),
    Column('AngebotErhaltenAm', DateTime),
    Column('Bemerkung', Text),
    Index('idx_angebotsanfrage_lieferant', 'LieferantID'),
    Index('idx_angebotsanfrage_erstellt_von', 'ErstelltVonID'),
    Index('idx_angebotsanfrage_abteilung', 'ErstellerAbteilungID'),
    Index('idx_angebotsanfrage_status', 'Status'),
)

AngebotsanfragePosition = Table(
    'AngebotsanfragePosition', metadata,
    _pk(),
    Column('AngebotsanfrageID', Integer, ForeignKey('Angebotsanfrage.ID', ondelete='CASCADE'), nullable=False),
    Column('ErsatzteilID', Integer, ForeignKey('Ersatzteil.ID')),
    Column('Menge', Integer, nullable=False),
    Column('Einheit', Text),
    Column('Bemerkung', Text),
    Column('Angebotspreis', Float),
    Column('Angebotswaehrung', Text),
    Column('Bestellnummer', Text),
    Column('Bezeichnung', Text),
    Column('Link', Text),
    Column('KostenstelleID', Integer, ForeignKey('Kostenstelle.ID')),
    Index('idx_angebotsanfrage_position_anfrage', 'AngebotsanfrageID'),
    Index('idx_angebotsanfrage_position_ersatzteil', 'ErsatzteilID'),
)

Bestellung = Table(
    'Bestellung', metadata,
    _pk(),
    Column('AngebotsanfrageID', Integer, ForeignKey('Angebotsanfrage.ID')),
    Column('LieferantID', Integer, ForeignKey('Lieferant.ID'), nullable=False),
    Column('ErstelltVonID', Integer, ForeignKey('Mitarbeiter.ID'), nullable=False),
    Column('ErstellerAbteilungID', Integer, ForeignKey('Abteilung.ID')),
    Column('Status', Text, nullable=False, server_default=text("'Erstellt'")),
    _ts_now('ErstelltAm'),
    Column('FreigegebenAm', DateTime),
    Column('FreigegebenVonID', Integer, ForeignKey('Mitarbeiter.ID')),
    Column('FreigabeBemerkung', Text),
    Column('BestelltAm', DateTime),
    Column('BestelltVonID', Integer, ForeignKey('Mitarbeiter.ID')),
    Column('Unterschrift', Text),
    Column('Gel\u00f6scht', Integer, nullable=False, server_default=text('0')),
    Column('Prioritaet', Integer, nullable=False, server_default=text('3')),
    Column('Lieferdatum', Text),
    Column('Bemerkung', Text),
    Index('idx_bestellung_angebotsanfrage', 'AngebotsanfrageID'),
    Index('idx_bestellung_lieferant', 'LieferantID'),
    Index('idx_bestellung_status', 'Status'),
    Index('idx_bestellung_erstellt_von', 'ErstelltVonID'),
    Index('idx_bestellung_abteilung', 'ErstellerAbteilungID'),
    Index('idx_bestellung_erstellt_am', 'ErstelltAm'),
)

BestellungPosition = Table(
    'BestellungPosition', metadata,
    _pk(),
    Column('BestellungID', Integer, ForeignKey('Bestellung.ID', ondelete='CASCADE'), nullable=False),
    Column('AngebotsanfragePositionID', Integer, ForeignKey('AngebotsanfragePosition.ID')),
    Column('ErsatzteilID', Integer, ForeignKey('Ersatzteil.ID')),
    Column('Menge', Integer, nullable=False),
    Column('Einheit', Text),
    Column('ErhalteneMenge', Integer, nullable=False, server_default=text('0')),
    Column('Bestellnummer', Text),
    Column('Bezeichnung', Text),
    Column('Bemerkung', Text),
    Column('Preis', Float),
    Column('Waehrung', Text),
    Column('Link', Text),
    Column('KostenstelleID', Integer, ForeignKey('Kostenstelle.ID')),
    Index('idx_bestellung_position_bestellung', 'BestellungID'),
    Index('idx_bestellung_position_ersatzteil', 'ErsatzteilID'),
    Index('idx_bestellung_position_angebotsanfrage', 'AngebotsanfragePositionID'),
)

BestellungSichtbarkeit = Table(
    'BestellungSichtbarkeit', metadata,
    _pk(),
    Column('BestellungID', Integer, ForeignKey('Bestellung.ID', ondelete='CASCADE'), nullable=False),
    Column('AbteilungID', Integer, ForeignKey('Abteilung.ID', ondelete='CASCADE'), nullable=False),
    _ts_now('ErstelltAm'),
    UniqueConstraint('BestellungID', 'AbteilungID'),
    Index('idx_bestellung_sichtbarkeit_bestellung', 'BestellungID'),
    Index('idx_bestellung_sichtbarkeit_abteilung', 'AbteilungID'),
)


# ---------------------------------------------------------------------------
# Berechtigungen
# ---------------------------------------------------------------------------

Berechtigung = Table(
    'Berechtigung', metadata,
    _pk(),
    Column('Schluessel', Text, nullable=False, unique=True),
    Column('Bezeichnung', Text, nullable=False),
    Column('Beschreibung', Text),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    Index('idx_berechtigung_schluessel', 'Schluessel'),
    Index('idx_berechtigung_aktiv', 'Aktiv'),
)

MitarbeiterBerechtigung = Table(
    'MitarbeiterBerechtigung', metadata,
    _pk(),
    Column('MitarbeiterID', Integer, ForeignKey('Mitarbeiter.ID', ondelete='CASCADE'), nullable=False),
    Column('BerechtigungID', Integer, ForeignKey('Berechtigung.ID', ondelete='CASCADE'), nullable=False),
    UniqueConstraint('MitarbeiterID', 'BerechtigungID'),
    Index('idx_mitarbeiter_berechtigung_ma', 'MitarbeiterID'),
    Index('idx_mitarbeiter_berechtigung_ber', 'BerechtigungID'),
)


# ---------------------------------------------------------------------------
# Print-Agent / Zebra / Etiketten
# ---------------------------------------------------------------------------

print_agents = Table(
    'print_agents', metadata,
    _pk_lower(),
    Column('name', Text, nullable=False, unique=True),
    Column('standort', Text),
    Column('token_hash', Text, nullable=False),
    Column('active', Integer, nullable=False, server_default=text('1')),
    Column('last_seen_at', Text),
    Column('last_ip', Text),
    Column('created_at', Text, server_default=text("(datetime('now'))")),
    Column('updated_at', Text, server_default=text("(datetime('now'))")),
    Index('idx_print_agents_active', 'active'),
)

zebra_printers = Table(
    'zebra_printers', metadata,
    _pk_lower(),
    Column('name', Text, nullable=False),
    Column('ip_address', Text, nullable=False),
    Column('description', Text),
    Column('ort', Text),
    Column('agent_id', Integer, ForeignKey('print_agents.id')),
    Column('active', Integer, nullable=False, server_default=text('1')),
    Column('created_at', Text, server_default=text("(datetime('now'))")),
    Column('updated_at', Text, server_default=text("(datetime('now'))")),
    Index('idx_zebra_printers_active', 'active'),
    Index('idx_zebra_printers_ip', 'ip_address'),
    Index('idx_zebra_printers_agent', 'agent_id'),
)

print_jobs = Table(
    'print_jobs', metadata,
    _pk_lower(),
    Column('agent_id', Integer, ForeignKey('print_agents.id'), nullable=False),
    Column('drucker_id', Integer, ForeignKey('zebra_printers.id'), nullable=False),
    Column('zpl', Text, nullable=False),
    Column('status', Text, nullable=False, server_default=text("'pending'")),
    Column('attempts', Integer, nullable=False, server_default=text('0')),
    Column('lease_until', Text),
    Column('error_message', Text),
    Column('created_by_mitarbeiter_id', Integer),
    Column('created_at', Text, server_default=text("(datetime('now'))")),
    Column('completed_at', Text),
    Index('idx_print_jobs_agent_status', 'agent_id', 'status'),
    Index('idx_print_jobs_created', 'created_at'),
)

label_formats = Table(
    'label_formats', metadata,
    _pk_lower(),
    Column('name', Text, nullable=False),
    Column('description', Text),
    Column('width_mm', Integer, nullable=False),
    Column('height_mm', Integer, nullable=False),
    Column('orientation', Text, nullable=False, server_default=text("'portrait'")),
    Column('zpl_header', Text, nullable=False),
    Column('zpl_zusatz', Text),
    Column('created_at', Text, server_default=text("(datetime('now'))")),
    Column('updated_at', Text, server_default=text("(datetime('now'))")),
    Index('idx_label_formats_name', 'name'),
)

Etikett = Table(
    'Etikett', metadata,
    _pk_lower(),
    Column('bezeichnung', Text, nullable=False),
    Column('etikettformat_id', Integer, ForeignKey('label_formats.id'), nullable=False),
    Column('druckbefehle', Text, nullable=False),
    Column('created_at', Text, server_default=text("(datetime('now'))")),
    Column('updated_at', Text, server_default=text("(datetime('now'))")),
    Index('idx_etikett_format', 'etikettformat_id'),
)

etikett_druck_konfig = Table(
    'etikett_druck_konfig', metadata,
    _pk_lower(),
    Column('funktion_code', Text, nullable=False),
    Column('etikett_id', Integer, ForeignKey('Etikett.id'), nullable=False),
    Column('drucker_id', Integer, ForeignKey('zebra_printers.id')),
    Column('prioritaet', Integer, nullable=False, server_default=text('0')),
    Column('aktiv', Integer, nullable=False, server_default=text('1')),
    Column('created_at', Text, server_default=text("(datetime('now'))")),
    Column('updated_at', Text, server_default=text("(datetime('now', 'localtime'))")),
    Index('idx_edk_funktion', 'funktion_code'),
    Index('idx_edk_etikett', 'etikett_id'),
    Index('idx_edk_aktiv', 'aktiv'),
)

etikett_druck_konfig_abteilung = Table(
    'etikett_druck_konfig_abteilung', metadata,
    Column('konfig_id', Integer, ForeignKey('etikett_druck_konfig.id', ondelete='CASCADE'), nullable=False),
    Column('abteilung_id', Integer, ForeignKey('Abteilung.ID'), nullable=False),
    PrimaryKeyConstraint('konfig_id', 'abteilung_id'),
    Index('idx_edka_abteilung', 'abteilung_id'),
)


# ---------------------------------------------------------------------------
# WebAuthn / Menue-Sichtbarkeit
# ---------------------------------------------------------------------------

WebAuthnCredential = Table(
    'WebAuthnCredential', metadata,
    _pk(),
    Column('MitarbeiterID', Integer, ForeignKey('Mitarbeiter.ID', ondelete='CASCADE'), nullable=False),
    Column('CredentialID', Text, nullable=False),
    Column('PublicKey', Text, nullable=False),
    Column('SignCount', Integer, nullable=False, server_default=text('0')),
    Column('UserHandle', Text),
    Column('Transports', Text),
    Column('Label', Text),
    _ts_now('ErstelltAm'),
    Column('LetzteVerwendung', DateTime),
    Column('Aktiv', Integer, nullable=False, server_default=text('1')),
    UniqueConstraint('MitarbeiterID', 'CredentialID'),
    Index('idx_webauthn_credential_mitarbeiter', 'MitarbeiterID'),
    Index('idx_webauthn_credential_aktiv', 'Aktiv'),
)

MitarbeiterMenueSichtbarkeit = Table(
    'MitarbeiterMenueSichtbarkeit', metadata,
    _pk(),
    Column('MitarbeiterID', Integer, ForeignKey('Mitarbeiter.ID', ondelete='CASCADE'), nullable=False),
    Column('MenueSchluessel', Text, nullable=False),
    Column('Sichtbar', Integer, nullable=False, server_default=text('1')),
    UniqueConstraint('MitarbeiterID', 'MenueSchluessel'),
    Index('idx_mitarbeiter_menue_sichtbarkeit_ma', 'MitarbeiterID'),
    Index('idx_mitarbeiter_menue_sichtbarkeit_menue', 'MenueSchluessel'),
)

# Prozesslokaler State-Cache fuer WebAuthn-Challenges (Registrierung / Login).
# Wird von ``utils.webauthn`` lazy gepflegt; via Alembic auf frischen DBs erzeugt.
WebAuthnState = Table(
    'WebAuthnState', metadata,
    Column('state_id', Text, primary_key=True),
    Column('payload', LargeBinary, nullable=False),
    Column('created_at', Integer, nullable=False),
    Column('expires_at', Integer, nullable=False),
    Index('IX_WebAuthnState_expires', 'expires_at'),
)


# Liste aller Kern-Tabellennamen, die vom App-Start-Healthcheck erwartet werden.
CORE_TABLE_NAMES = tuple(t.name for t in metadata.sorted_tables)
