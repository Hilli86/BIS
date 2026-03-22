"""Tests für utils.database_check_helpers (SQLite-Hilfen)."""

import sqlite3

from utils.database_check_helpers import (
    column_exists,
    create_column_if_not_exists,
    create_index_if_not_exists,
    create_table_if_not_exists,
    index_exists,
    table_exists,
)


def test_table_exists_and_column_exists(tmp_path):
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    assert table_exists(conn, "demo") is True
    assert table_exists(conn, "other") is False
    assert column_exists(conn, "demo", "name") is True
    assert column_exists(conn, "demo", "missing") is False
    conn.close()


def test_create_table_if_not_exists_creates_table(tmp_path):
    db = tmp_path / "t2.db"
    conn = sqlite3.connect(db)
    created = create_table_if_not_exists(
        conn,
        "X",
        "CREATE TABLE X (id INTEGER PRIMARY KEY)",
    )
    assert created is True
    assert table_exists(conn, "X") is True
    created_again = create_table_if_not_exists(
        conn,
        "X",
        "CREATE TABLE X (id INTEGER PRIMARY KEY)",
    )
    assert created_again is False
    conn.close()


def test_create_column_if_not_exists(tmp_path):
    db = tmp_path / "t3.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE y (id INTEGER PRIMARY KEY)")
    conn.commit()
    assert column_exists(conn, "y", "extra") is False
    create_column_if_not_exists(conn, "y", "extra", "ALTER TABLE y ADD COLUMN extra TEXT")
    assert column_exists(conn, "y", "extra") is True
    conn.close()


def test_index_exists_and_create_index(tmp_path):
    db = tmp_path / "t4.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE z (id INTEGER, name TEXT)")
    conn.execute("CREATE INDEX idx_z_name ON z(name)")
    conn.commit()
    assert index_exists(conn, "idx_z_name") is True
    created = create_index_if_not_exists(
        conn,
        "idx_z_id",
        "CREATE INDEX idx_z_id ON z(id)",
    )
    assert created is True
    assert index_exists(conn, "idx_z_id") is True
    conn.close()
