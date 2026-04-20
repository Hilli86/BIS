"""
Datenmigration SQLite -> Postgres fuer BIS (einmaliger Umzug).

Phase 5 der SA-Migration: Das Schema wird in beiden Welten ueber Alembic
deklariert (``utils.db_schema``), deshalb reicht eine **datengetriebene**
Kopie ohne DDL. Dieses Skript liest alle Tabellen aus einer Quell-Engine
(Default: SQLite) und schreibt sie tabellenweise in eine Ziel-Engine
(Default: Postgres).

Ablauf auf dem Zielsystem:

1. Leere Postgres-Datenbank anlegen (``createdb bis``).
2. Auf der Postgres-DB einmalig ``alembic upgrade head`` ausfuehren, damit das
   Schema identisch zu SQLite ist (gleiche Tabellennamen, Spaltennamen,
   Constraints, Indizes).
3. Dieses Skript starten – es kopiert Zeilen tabellenweise in topologischer
   Reihenfolge der Foreign Keys.
4. Sequenzen in Postgres auf ``MAX(id)+1`` setzen (erfolgt automatisch am
   Ende).

Beispiel (PowerShell):

    $env:SOURCE_URL = "sqlite:///C:/BIS-Daten/database_main.db"
    $env:TARGET_URL = "postgresql+psycopg://bis:secret@localhost:5432/bis"
    py scripts/migrate_sqlite_to_postgres.py

Parameter (Umgebungsvariablen):

    SOURCE_URL     Quell-DB (SA-URL). Default: sqlite:///database_main.db
    TARGET_URL     Ziel-DB (SA-URL). Pflicht, wenn != SOURCE_URL.
    BATCH_SIZE     Zeilen pro INSERT-Batch (Default: 500).
    TRUNCATE       "1" = Zieltabellen vor dem Kopieren leeren (Default: "0").

Nicht abgedeckt (bewusst):

- Schema-Migration (wird von Alembic erledigt).
- Large-Object / BLOB-Streaming jenseits ``LargeBinary`` in normalen Spalten.
- Inkrementelles Delta (dieses Skript ist fuer den *einmaligen* Umzug gedacht;
  danach ist Postgres die fuehrende DB).

Alternative: ``pgloader sqlite:///pfad.db postgresql://...`` – siehe
``docs/POSTGRES_DEPLOYMENT.md``.
"""

from __future__ import annotations

import os
import sys
from typing import Iterable

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from sqlalchemy import (  # noqa: E402
    MetaData,
    Table,
    create_engine,
    delete,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Engine  # noqa: E402

from utils.database import normalize_db_url  # noqa: E402
from utils.db_schema import metadata as schema_metadata  # noqa: E402


def _resolve_urls() -> tuple[str, str]:
    source = os.environ.get('SOURCE_URL') or 'sqlite:///database_main.db'
    target = os.environ.get('TARGET_URL')
    if not target:
        print('[FEHLER] TARGET_URL nicht gesetzt.')
        print('         Beispiel: TARGET_URL=postgresql+psycopg://bis:secret@localhost/bis')
        sys.exit(2)
    source_norm = normalize_db_url(source)
    target_norm = normalize_db_url(target)
    if source_norm == target_norm:
        print(f'[FEHLER] SOURCE_URL und TARGET_URL sind identisch ({source_norm}).')
        sys.exit(2)
    return source_norm, target_norm


def _ordered_tables() -> list[Table]:
    """Tabellen in Insert-Reihenfolge (Eltern vor Kindern)."""
    return list(schema_metadata.sorted_tables)


def _copy_table(
    source: Engine,
    target: Engine,
    table: Table,
    *,
    batch_size: int,
    truncate: bool,
    source_tables: set[str],
) -> int:
    """Kopiert eine einzelne Tabelle. Gibt die Anzahl kopierter Zeilen zurueck."""
    if table.name not in source_tables:
        # Tabelle existiert in der Quelle nicht (z. B. neu hinzugekommenes
        # Feature, das in der alten SQLite-DB noch nie migriert wurde). Fuer
        # den Umzug ist das harmlos, solange die Zieltabelle leer bleibt.
        print(f'  [SKIP] {table.name}: in der Quelle nicht vorhanden')
        return 0

    columns = [c.name for c in table.columns]

    with source.connect() as src_conn:
        total = src_conn.execute(
            select(text('COUNT(*)')).select_from(table)
        ).scalar_one()

    if total == 0:
        print(f'  [SKIP] {table.name}: leer in der Quelle')
        return 0

    with target.begin() as tgt_conn:
        if truncate:
            tgt_conn.execute(delete(table))

    copied = 0
    with source.connect() as src_conn:
        result = src_conn.execution_options(stream_results=True).execute(select(table))
        batch: list[dict] = []
        with target.begin() as tgt_conn:
            for row in result.mappings():
                batch.append({k: row[k] for k in columns})
                if len(batch) >= batch_size:
                    tgt_conn.execute(table.insert(), batch)
                    copied += len(batch)
                    batch.clear()
                    print(f'  {table.name}: {copied}/{total} ...')
            if batch:
                tgt_conn.execute(table.insert(), batch)
                copied += len(batch)

    print(f'  [OK] {table.name}: {copied} Zeilen')
    return copied


def _reset_postgres_sequences(target: Engine, tables: Iterable[Table]) -> None:
    """Setzt Postgres-IDENTITY/SERIAL-Sequenzen auf MAX(id)+1.

    Ohne diesen Schritt vergibt Postgres nach dem Bulk-Insert beim naechsten
    regulaeren INSERT wieder die ID 1 und kollidiert mit den importierten
    Primaerschluesseln.
    """
    if target.dialect.name != 'postgresql':
        return

    print()
    print('[INFO] Setze Postgres-Sequenzen auf MAX(id)+1 ...')
    with target.begin() as conn:
        for table in tables:
            pk_cols = [c for c in table.columns if c.primary_key and c.autoincrement]
            if len(pk_cols) != 1:
                continue
            pk = pk_cols[0]
            seq_sql = text(
                "SELECT pg_get_serial_sequence(:tbl, :col) AS seq_name"
            )
            row = conn.execute(
                seq_sql, {'tbl': table.name, 'col': pk.name}
            ).first()
            seq_name = row[0] if row else None
            if not seq_name:
                continue
            try:
                conn.execute(
                    text(
                        f'SELECT setval(:seq, '
                        f'COALESCE((SELECT MAX("{pk.name}") FROM "{table.name}"), 0) + 1, '
                        f'false)'
                    ),
                    {'seq': seq_name},
                )
                print(f'  [OK] {table.name}.{pk.name} -> {seq_name}')
            except Exception as exc:  # pragma: no cover - defensiv
                print(f'  [WARN] {table.name}.{pk.name}: {exc}')


def _verify(
    source: Engine,
    target: Engine,
    tables: Iterable[Table],
    source_tables: set[str],
) -> list[str]:
    """Vergleicht Zeilenzahlen zwischen Quelle und Ziel; liefert Abweichungen."""
    mismatches: list[str] = []
    with source.connect() as src, target.connect() as tgt:
        for table in tables:
            if table.name not in source_tables:
                continue
            try:
                src_n = src.execute(select(text('COUNT(*)')).select_from(table)).scalar_one()
                tgt_n = tgt.execute(select(text('COUNT(*)')).select_from(table)).scalar_one()
            except Exception as exc:  # pragma: no cover - defensiv
                mismatches.append(f'{table.name}: Zaehlfehler ({exc})')
                continue
            if src_n != tgt_n:
                mismatches.append(f'{table.name}: Quelle={src_n}, Ziel={tgt_n}')
    return mismatches


def _ensure_target_schema_present(target: Engine) -> None:
    """Sanity-Check: Sind die Schema-Tabellen im Ziel vorhanden?"""
    inspector = inspect(target)
    existing = set(inspector.get_table_names())
    expected = {t.name for t in schema_metadata.sorted_tables}
    missing = sorted(expected - existing)
    if missing:
        print('[FEHLER] Zieldatenbank enthaelt nicht alle Schema-Tabellen.')
        print('         Bitte vorher "alembic upgrade head" gegen die Ziel-DB laufen lassen.')
        print('         Fehlend:', ', '.join(missing[:20]),
              '...' if len(missing) > 20 else '')
        sys.exit(3)


def main() -> None:
    source_url, target_url = _resolve_urls()
    batch_size = int(os.environ.get('BATCH_SIZE', '500') or '500')
    truncate = (os.environ.get('TRUNCATE', '0').lower() in ('1', 'true', 'yes'))

    print('=' * 70)
    print('  BIS - Datenmigration (SQLite -> Postgres)')
    print('=' * 70)
    print(f'  Quelle: {source_url}')
    print(f'  Ziel:   {target_url}')
    print(f'  Batch:  {batch_size}  Truncate: {truncate}')
    print()

    source = create_engine(source_url, future=True)
    target = create_engine(target_url, future=True, pool_pre_ping=True)

    try:
        _ensure_target_schema_present(target)

        src_inspector = inspect(source)
        source_tables = set(src_inspector.get_table_names())

        tables = _ordered_tables()
        print(f'[INFO] Kopiere {len(tables)} Tabellen in topologischer Reihenfolge ...')
        total_rows = 0
        for table in tables:
            total_rows += _copy_table(
                source, target, table,
                batch_size=batch_size, truncate=truncate,
                source_tables=source_tables,
            )

        _reset_postgres_sequences(target, tables)

        print()
        print('[INFO] Verifikation (Zeilenzahlen) ...')
        # Reflektierte Tabellen verwenden, damit ``select(COUNT(*)).select_from``
        # auch gegen das tatsaechliche Zielschema zaehlt (und beim Vergleich mit
        # der Quelle keine fehlenden Tabellen mitgezaehlt werden).
        present = [t for t in tables if t.name in source_tables]
        reflected = MetaData()
        reflected.reflect(bind=target, only=[t.name for t in present])
        mismatches = _verify(
            source, target,
            [reflected.tables[t.name] for t in present],
            source_tables,
        )
        if mismatches:
            print('[WARN] Zeilenzahlen weichen ab:')
            for m in mismatches:
                print(f'  - {m}')
            sys.exit(4)

        print()
        print('=' * 70)
        print(f'  [ERFOLG] {total_rows} Zeilen uebertragen, Zeilenzahlen ident.')
        print('=' * 70)
    finally:
        source.dispose()
        target.dispose()


if __name__ == '__main__':
    main()
