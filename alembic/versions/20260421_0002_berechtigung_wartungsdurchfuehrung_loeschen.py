"""berechtigung darf_Wartungsdurchfuehrung_loeschen

Revision ID: 0002_ber_wd_loeschen
Revises: 0001_baseline
Create Date: 2026-04-21

Legt die Berechtigung ``darf_Wartungsdurchführung_löschen`` an, falls sie noch
nicht existiert. Die Migration ist dialektneutral (SELECT/INSERT statt
``INSERT OR IGNORE``).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = '0002_ber_wd_loeschen'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None


_SCHLUESSEL = 'darf_Wartungsdurchführung_löschen'
_BEZEICHNUNG = 'Darf Wartungsdurchführung löschen'
_BESCHREIBUNG = (
    'Erlaubt das Löschen protokollierter Wartungsdurchführungen inkl. Serviceberichten'
)


def upgrade() -> None:
    bind = op.get_bind()
    vorhanden = bind.execute(
        sa.text('SELECT 1 FROM Berechtigung WHERE Schluessel = :k'),
        {'k': _SCHLUESSEL},
    ).scalar()
    if vorhanden:
        return
    bind.execute(
        sa.text(
            'INSERT INTO Berechtigung (Schluessel, Bezeichnung, Beschreibung, Aktiv) '
            'VALUES (:k, :b, :d, 1)'
        ),
        {'k': _SCHLUESSEL, 'b': _BEZEICHNUNG, 'd': _BESCHREIBUNG},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text('DELETE FROM Berechtigung WHERE Schluessel = :k'),
        {'k': _SCHLUESSEL},
    )
