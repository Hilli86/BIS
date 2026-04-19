"""Token-Auth-Tests fuer den /api/agent/* Blueprint."""

import sqlite3
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from utils.zebra_client import hash_agent_token


@pytest.fixture
def temp_db(tmp_path):
    """In-Memory-DB mit Mindestschema fuer print_agents/print_jobs/zebra_printers."""
    db_path = tmp_path / 'test.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE print_agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            standort TEXT,
            token_hash TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            last_seen_at TEXT,
            last_ip TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE zebra_printers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            description TEXT,
            ort TEXT,
            agent_id INTEGER,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE print_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            drucker_id INTEGER NOT NULL,
            zpl TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            lease_until TEXT,
            error_message TEXT,
            created_by_mitarbeiter_id INTEGER,
            created_at TEXT,
            completed_at TEXT
        );
    ''')
    conn.execute(
        '''INSERT INTO print_agents (name, token_hash, active) VALUES (?, ?, 1)''',
        ('test-agent', hash_agent_token('valid-token-123')),
    )
    conn.execute(
        '''INSERT INTO zebra_printers (name, ip_address, agent_id, active)
           VALUES ('Drucker', '10.0.0.5', 1, 1)''',
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def patched_app(temp_db):
    """Patch utils.database.get_db_connection so der Blueprint die Test-DB nutzt."""
    @contextmanager
    def _fake_conn():
        yield temp_db

    with patch('modules.print_agent.routes.get_db_connection', _fake_conn):
        from app import app
        app.config['TESTING'] = True
        yield app


def _client(app):
    return app.test_client()


def test_poll_without_token_401(patched_app):
    r = _client(patched_app).post('/api/agent/poll')
    assert r.status_code == 401


def test_poll_with_invalid_token_401(patched_app):
    r = _client(patched_app).post(
        '/api/agent/poll', headers={'Authorization': 'Bearer wrong'}
    )
    assert r.status_code == 401


def test_poll_with_valid_token_returns_no_job_when_queue_empty(patched_app):
    r = _client(patched_app).post(
        '/api/agent/poll', headers={'Authorization': 'Bearer valid-token-123'}
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data == {'success': True, 'job': None}


def test_poll_returns_pending_job(patched_app, temp_db):
    temp_db.execute(
        '''INSERT INTO print_jobs
               (agent_id, drucker_id, zpl, status, attempts, created_at)
           VALUES (1, 1, '^XA^XZ', 'pending', 0, datetime('now'))''',
    )
    temp_db.commit()
    r = _client(patched_app).post(
        '/api/agent/poll', headers={'Authorization': 'Bearer valid-token-123'}
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['job'] is not None
    assert data['job']['zpl'] == '^XA^XZ'
    assert data['job']['drucker_ip'] == '10.0.0.5'
    row = temp_db.execute('SELECT status FROM print_jobs').fetchone()
    assert row['status'] == 'leased'


def test_done_endpoint_marks_job_done(patched_app, temp_db):
    temp_db.execute(
        '''INSERT INTO print_jobs (agent_id, drucker_id, zpl, status, attempts)
           VALUES (1, 1, '^X', 'leased', 1)''',
    )
    temp_db.commit()
    job_id = temp_db.execute('SELECT id FROM print_jobs').fetchone()['id']
    r = _client(patched_app).post(
        f'/api/agent/jobs/{job_id}/done',
        headers={'Authorization': 'Bearer valid-token-123'},
    )
    assert r.status_code == 200
    row = temp_db.execute('SELECT status FROM print_jobs WHERE id = ?', (job_id,)).fetchone()
    assert row['status'] == 'done'


def test_heartbeat_updates_last_seen(patched_app, temp_db):
    r = _client(patched_app).post(
        '/api/agent/heartbeat', headers={'Authorization': 'Bearer valid-token-123'}
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['agent_name'] == 'test-agent'
    row = temp_db.execute('SELECT last_seen_at FROM print_agents').fetchone()
    assert row['last_seen_at'] is not None
