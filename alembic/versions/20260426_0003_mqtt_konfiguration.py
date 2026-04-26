"""mqtt konfiguration tabelle

Revision ID: 0003_mqtt_konf
Revises: 0002_ber_wd_loeschen
Create Date: 2026-04-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = '0003_mqtt_konf'
down_revision = '0002_ber_wd_loeschen'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'MqttKonfiguration' in insp.get_table_names():
        return
    op.create_table(
        'MqttKonfiguration',
        sa.Column('ID', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('Aktiv', sa.Integer, nullable=False, server_default='0'),
        sa.Column('BrokerHost', sa.Text, nullable=True),
        sa.Column('BrokerPort', sa.Integer, nullable=False, server_default='1883'),
        sa.Column('UseTls', sa.Integer, nullable=False, server_default='0'),
        sa.Column('TlsInsecure', sa.Integer, nullable=False, server_default='0'),
        sa.Column('CaPfad', sa.Text, nullable=True),
        sa.Column('Benutzername', sa.Text, nullable=True),
        sa.Column('PasswortKrypt', sa.Text, nullable=True),
        sa.Column('TopicPrefixBeleuchtung', sa.Text, nullable=False),
        sa.Column('MqttClientId', sa.Text, nullable=True),
        sa.Column('RedisUrl', sa.Text, nullable=True),
        sa.Column('GeaendertAm', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    )
    op.create_index('idx_mqtt_konf_aktiv', 'MqttKonfiguration', ['Aktiv'])
    bind.execute(
        sa.text(
            "INSERT INTO MqttKonfiguration (Aktiv, BrokerPort, TopicPrefixBeleuchtung) "
            "VALUES (0, 1883, 'IPS/BM/Beleuchtung')"
        )
    )


def downgrade() -> None:
    op.drop_index('idx_mqtt_konf_aktiv', table_name='MqttKonfiguration')
    op.drop_table('MqttKonfiguration')
