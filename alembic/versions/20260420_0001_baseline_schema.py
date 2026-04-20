"""baseline schema (Phase 1)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-20

Diese Migration ist der Einstiegspunkt fuer die Alembic-Versionierung. Sie legt
das komplette BIS-Schema an, so wie es in ``utils.db_schema`` deklariert ist.

Das bewusste Vorgehen:

- ``op.get_bind()`` + ``metadata.create_all(checkfirst=True)``: Auf einer
  frischen Datenbank werden alle Tabellen und Indizes angelegt. Auf einer
  bestehenden Datenbank (Upgrade-Pfad aus der Pre-Alembic-Zeit) passiert
  nichts, weil jede Tabelle bereits existiert (``checkfirst=True``).
- Anschliessend reicht ``alembic stamp head`` bzw. ``alembic upgrade head``
  auf der Produktions-DB, ohne Daten zu beruehren.

Fuer zukuenftige Schemaaenderungen werden neue, kleine Migrationen mit
expliziten ``op.add_column``/``op.create_table``-Aufrufen angelegt.
"""

from __future__ import annotations

from alembic import op

from utils.db_schema import metadata

revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    metadata.drop_all(bind=bind, checkfirst=True)
