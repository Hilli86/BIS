"""
Datenbank-Initialisierungsskript fuer BIS (SA-Fassade + Alembic).

Phase 4 der SA-Migration: Schema wird ueber Alembic angelegt
(``alembic upgrade head``), Seed-Daten (BIS-Admin-Abteilung und -Benutzer)
ueber ``utils.database.get_db_connection()`` geschrieben. Damit funktioniert
das Skript sowohl gegen SQLite (Default) als auch gegen Postgres – abhaengig
von der Umgebungsvariable ``DATABASE_URL``.

Aufruf aus dem Projektroot:
    py scripts/init_database.py

Umgebung:
    DATABASE_URL   Standard: ``database_main.db`` (wird zu ``sqlite:///...``
                   normalisiert); alternativ volle SA-URL wie
                   ``postgresql+psycopg://user:pw@host/db``.
"""

from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from werkzeug.security import generate_password_hash
except ImportError:
    print("\n[FEHLER] Das Modul 'werkzeug' ist nicht installiert.")
    print("\nBitte fuehren Sie zuerst aus:")
    print("  pip install -r requirements.txt")
    sys.exit(1)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402

from utils.database import normalize_db_url  # noqa: E402
from utils.db_schema import Abteilung, Mitarbeiter  # noqa: E402


def _resolve_database_url() -> str:
    raw = os.environ.get('DATABASE_URL') or 'database_main.db'
    return normalize_db_url(raw)


def _run_alembic_upgrade(db_url: str) -> None:
    ini_path = os.path.join(_PROJECT_ROOT, 'alembic.ini')
    cfg = Config(ini_path)
    cfg.set_main_option('script_location', os.path.join(_PROJECT_ROOT, 'alembic'))
    cfg.set_main_option('sqlalchemy.url', db_url)
    os.environ['DATABASE_URL'] = db_url

    print(f"[INFO] Fuehre 'alembic upgrade head' aus (url={db_url}) ...")
    command.upgrade(cfg, 'head')
    print('[OK] Schema-Migrationen angewendet')


def _seed_admin(db_url: str) -> str | None:
    """Legt BIS-Admin-Abteilung und -Benutzer an, falls noch nicht vorhanden.

    Verwendet SA-Core-Inserts, damit das Skript dialektunabhaengig bleibt
    (SQLite: ``?``, Postgres: ``%s`` werden automatisch aus den benannten
    Parametern gerendert).

    Gibt das einmalige Initial-Passwort zurueck (``None`` wenn der Benutzer
    bereits existierte).
    """
    engine = create_engine(db_url, future=True, pool_pre_ping=True)
    initial_passwort: str | None = None

    try:
        with engine.begin() as conn:
            abt_row = conn.execute(
                select(Abteilung.c.ID).where(Abteilung.c.Bezeichnung == 'BIS-Admin')
            ).first()
            if abt_row is not None:
                abteilung_id = abt_row[0]
                print(f"[SKIP] Abteilung 'BIS-Admin' existiert bereits (ID: {abteilung_id})")
            else:
                result = conn.execute(
                    Abteilung.insert().values(
                        Bezeichnung='BIS-Admin',
                        ParentAbteilungID=None,
                        Aktiv=1,
                        Sortierung=0,
                    )
                )
                abteilung_id = result.inserted_primary_key[0]
                print(f"[OK] Abteilung 'BIS-Admin' erstellt (ID: {abteilung_id})")

            ma_row = conn.execute(
                select(Mitarbeiter.c.ID).where(Mitarbeiter.c.Personalnummer == '99999')
            ).first()
            if ma_row is not None:
                user_id = ma_row[0]
                print(f"[SKIP] Benutzer 'BIS-Admin' existiert bereits (ID: {user_id})")
            else:
                import secrets as _secrets

                initial_passwort = _secrets.token_urlsafe(18)
                passwort_hash = generate_password_hash(initial_passwort)
                result = conn.execute(
                    Mitarbeiter.insert().values(
                        Personalnummer='99999',
                        Vorname='',
                        Nachname='BIS-Admin',
                        Aktiv=1,
                        Passwort=passwort_hash,
                        PrimaerAbteilungID=abteilung_id,
                        PasswortWechselErforderlich=1,
                    )
                )
                user_id = result.inserted_primary_key[0]
                print(f"[OK] Benutzer 'BIS-Admin' erstellt (ID: {user_id})")
    finally:
        engine.dispose()

    return initial_passwort


def init_database() -> None:
    print("=" * 70)
    print("  BIS - Datenbank-Initialisierung")
    print("=" * 70)
    print()

    db_url = _resolve_database_url()
    try:
        _run_alembic_upgrade(db_url)
    except Exception as exc:
        print(f"\n[FEHLER] Alembic-Migration fehlgeschlagen: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    print()
    print("=" * 70)
    print("  Erstelle BIS-Admin Abteilung und Benutzer")
    print("=" * 70)
    print()

    try:
        initial_passwort = _seed_admin(db_url)
    except Exception as exc:
        print(f"\n[FEHLER] Seed fehlgeschlagen: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    print()
    print("=" * 70)
    print("  [ERFOLG] Datenbank erfolgreich initialisiert!")
    print("=" * 70)
    print()
    if initial_passwort:
        print("Login-Daten (einmalig, bitte sicher notieren):")
        print("  Personalnummer: 99999")
        print(f"  Passwort:       {initial_passwort}")
        print("  Hinweis: Beim ersten Login ist eine Passwort-Aenderung erforderlich.")
    else:
        print("Bestehender BIS-Admin wurde beibehalten; kein neues Passwort gesetzt.")
    print()


if __name__ == '__main__':
    init_database()
