"""Tests für utils.database_check_helpers (SQLite-Intro-Hilfen).

Die Helfer basieren auf SQLite-spezifischen Mitteln (``PRAGMA``,
``sqlite_master``) und bleiben fuer Diagnose-Zwecke SQLite-zentriert. Seit
Phase 4 nutzen die Tests die gemeinsame ``connection``-Fixture (in-memory
SQLite), damit sie frei von temporaeren Dateipfaden sind.
"""

from utils.database_check_helpers import (
    column_exists,
    create_column_if_not_exists,
    create_index_if_not_exists,
    create_table_if_not_exists,
    index_exists,
    table_exists,
)


def test_table_exists_and_column_exists(connection):
    connection.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, name TEXT)")
    connection.commit()
    assert table_exists(connection, "demo") is True
    assert table_exists(connection, "other") is False
    assert column_exists(connection, "demo", "name") is True
    assert column_exists(connection, "demo", "missing") is False


def test_create_table_if_not_exists_creates_table(connection):
    created = create_table_if_not_exists(
        connection,
        "X",
        "CREATE TABLE X (id INTEGER PRIMARY KEY)",
    )
    assert created is True
    assert table_exists(connection, "X") is True
    created_again = create_table_if_not_exists(
        connection,
        "X",
        "CREATE TABLE X (id INTEGER PRIMARY KEY)",
    )
    assert created_again is False


def test_create_column_if_not_exists(connection):
    connection.execute("CREATE TABLE y (id INTEGER PRIMARY KEY)")
    connection.commit()
    assert column_exists(connection, "y", "extra") is False
    create_column_if_not_exists(connection, "y", "extra", "ALTER TABLE y ADD COLUMN extra TEXT")
    assert column_exists(connection, "y", "extra") is True


def test_index_exists_and_create_index(connection):
    connection.execute("CREATE TABLE z (id INTEGER, name TEXT)")
    connection.execute("CREATE INDEX idx_z_name ON z(name)")
    connection.commit()
    assert index_exists(connection, "idx_z_name") is True
    created = create_index_if_not_exists(
        connection,
        "idx_z_id",
        "CREATE INDEX idx_z_id ON z(id)",
    )
    assert created is True
    assert index_exists(connection, "idx_z_id") is True
