"""Tests fuer Hybrid-Druck (utils.zebra_client.dispatch_print, Queue, Tokens)."""

import sqlite3
from datetime import datetime, timedelta, timezone


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)
from unittest.mock import patch

import pytest

from utils import zebra_client
from utils.etikett_druck import resolve_printer_agent_id
from utils.zebra_client import (
    cleanup_old_jobs,
    dispatch_print,
    enqueue_print_job,
    generate_agent_token,
    hash_agent_token,
    lease_next_job,
    mark_job_done,
    mark_job_error,
    recover_expired_leases,
    verify_agent_token,
    wait_for_job,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.execute('''CREATE TABLE print_agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        standort TEXT,
        token_hash TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        last_seen_at TEXT,
        last_ip TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')
    c.execute('''CREATE TABLE zebra_printers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        ip_address TEXT NOT NULL,
        description TEXT,
        ort TEXT,
        agent_id INTEGER,
        active INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (agent_id) REFERENCES print_agents(id)
    )''')
    c.execute('''CREATE TABLE print_jobs (
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
    )''')
    c.commit()
    yield c
    c.close()


def _seed_agent(conn, name='standort-a', token='secret-token'):
    conn.execute(
        '''INSERT INTO print_agents (name, token_hash, active, created_at, updated_at)
           VALUES (?, ?, 1, datetime('now'), datetime('now'))''',
        (name, hash_agent_token(token)),
    )
    conn.commit()
    return conn.execute('SELECT id FROM print_agents WHERE name = ?', (name,)).fetchone()['id']


def _seed_printer(conn, ip='10.0.0.5', agent_id=None):
    conn.execute(
        '''INSERT INTO zebra_printers (name, ip_address, agent_id, active)
           VALUES (?, ?, ?, 1)''',
        ('Test-Drucker', ip, agent_id),
    )
    conn.commit()
    return conn.execute(
        'SELECT id FROM zebra_printers WHERE ip_address = ?', (ip,)
    ).fetchone()['id']


# --------------------------------------------------------------------------
# Token-Helfer
# --------------------------------------------------------------------------


def test_token_hash_and_verify():
    t = generate_agent_token()
    assert isinstance(t, str) and len(t) >= 30
    h = hash_agent_token(t)
    assert verify_agent_token(t, h) is True
    assert verify_agent_token(t + 'x', h) is False
    assert verify_agent_token('', h) is False
    assert verify_agent_token(t, '') is False


# --------------------------------------------------------------------------
# dispatch_print: Direkt vs. Agent
# --------------------------------------------------------------------------


def test_dispatch_print_direct_calls_send(conn):
    drucker_id = _seed_printer(conn, agent_id=None)
    with patch.object(zebra_client, 'send_zpl_to_printer') as m:
        result = dispatch_print(conn, drucker_id, '^XA^XZ', mitarbeiter_id=1)
    assert result == {'mode': 'direct', 'ok': True}
    m.assert_called_once_with('10.0.0.5', '^XA^XZ')
    rows = conn.execute('SELECT COUNT(*) AS n FROM print_jobs').fetchone()
    assert rows['n'] == 0


def test_dispatch_print_direct_failure_returns_error(conn):
    drucker_id = _seed_printer(conn, agent_id=None)
    with patch.object(zebra_client, 'send_zpl_to_printer', side_effect=ConnectionError('refused')):
        result = dispatch_print(conn, drucker_id, '^XA^XZ')
    assert result['mode'] == 'direct'
    assert result['ok'] is False
    assert 'refused' in result['error_message']


def test_dispatch_print_agent_enqueues(conn):
    agent_id = _seed_agent(conn)
    drucker_id = _seed_printer(conn, agent_id=agent_id)
    result = dispatch_print(conn, drucker_id, '^XA^XZ', mitarbeiter_id=42, wait_seconds=0)
    assert result['mode'] == 'agent'
    assert result['ok'] is True
    assert result['status'] == 'pending'
    job = conn.execute(
        'SELECT agent_id, drucker_id, zpl, status, created_by_mitarbeiter_id FROM print_jobs WHERE id = ?',
        (result['job_id'],),
    ).fetchone()
    assert job['agent_id'] == agent_id
    assert job['drucker_id'] == drucker_id
    assert job['zpl'] == '^XA^XZ'
    assert job['status'] == 'pending'
    assert job['created_by_mitarbeiter_id'] == 42


def test_dispatch_print_unknown_drucker(conn):
    result = dispatch_print(conn, 9999, '^XA^XZ')
    assert result['ok'] is False
    assert 'nicht gefunden' in result['error_message'].lower()


def test_resolve_printer_agent_id(conn):
    agent_id = _seed_agent(conn)
    direkt = _seed_printer(conn, ip='10.0.0.6', agent_id=None)
    via_agent = _seed_printer(conn, ip='10.0.0.7', agent_id=agent_id)
    assert resolve_printer_agent_id(conn, direkt) is None
    assert resolve_printer_agent_id(conn, via_agent) == agent_id
    assert resolve_printer_agent_id(conn, 9999) is None
    assert resolve_printer_agent_id(conn, None) is None


def test_enqueue_requires_agent(conn):
    drucker_id = _seed_printer(conn, agent_id=None)
    with pytest.raises(ValueError):
        enqueue_print_job(conn, drucker_id, '^XA^XZ')


# --------------------------------------------------------------------------
# Queue / Lease / Recovery
# --------------------------------------------------------------------------


def test_lease_next_job_picks_pending_and_increments_attempts(conn):
    agent_id = _seed_agent(conn)
    drucker_id = _seed_printer(conn, agent_id=agent_id)
    job_id = enqueue_print_job(conn, drucker_id, '^XA^XZ')
    leased = lease_next_job(conn, agent_id)
    assert leased is not None
    assert leased['id'] == job_id
    assert leased['attempts'] == 1
    assert leased['drucker_ip'] == '10.0.0.5'
    again = conn.execute('SELECT status FROM print_jobs WHERE id = ?', (job_id,)).fetchone()
    assert again['status'] == 'leased'
    assert lease_next_job(conn, agent_id) is None


def test_lease_next_job_only_for_own_agent(conn):
    agent_a = _seed_agent(conn, name='agent-a', token='ta')
    agent_b = _seed_agent(conn, name='agent-b', token='tb')
    drucker_a = _seed_printer(conn, ip='10.0.0.10', agent_id=agent_a)
    enqueue_print_job(conn, drucker_a, '^XA^XZ')
    assert lease_next_job(conn, agent_b) is None
    assert lease_next_job(conn, agent_a) is not None


def test_mark_job_done_sets_completed(conn):
    agent_id = _seed_agent(conn)
    drucker_id = _seed_printer(conn, agent_id=agent_id)
    job_id = enqueue_print_job(conn, drucker_id, '^XA^XZ')
    lease_next_job(conn, agent_id)
    assert mark_job_done(conn, agent_id, job_id) is True
    row = conn.execute(
        'SELECT status, completed_at FROM print_jobs WHERE id = ?', (job_id,)
    ).fetchone()
    assert row['status'] == 'done'
    assert row['completed_at'] is not None


def test_mark_job_error_retries_then_fails(conn):
    agent_id = _seed_agent(conn)
    drucker_id = _seed_printer(conn, agent_id=agent_id)
    job_id = enqueue_print_job(conn, drucker_id, '^XA^XZ')
    for i in range(zebra_client.PRINT_JOB_MAX_ATTEMPTS):
        leased = lease_next_job(conn, agent_id)
        assert leased is not None
        assert mark_job_error(conn, agent_id, job_id, f'fehler {i}') is True
    row = conn.execute(
        'SELECT status, error_message FROM print_jobs WHERE id = ?', (job_id,)
    ).fetchone()
    assert row['status'] == 'error'
    assert 'fehler' in row['error_message']


def test_recover_expired_leases(conn):
    agent_id = _seed_agent(conn)
    drucker_id = _seed_printer(conn, agent_id=agent_id)
    conn.execute(
        '''INSERT INTO print_jobs
               (agent_id, drucker_id, zpl, status, attempts, lease_until, created_at)
           VALUES (?, ?, '^XA^XZ', 'leased', 1, ?, datetime('now'))''',
        (agent_id, drucker_id, (_utcnow() - timedelta(seconds=120)).strftime('%Y-%m-%d %H:%M:%S')),
    )
    conn.commit()
    n = recover_expired_leases(conn)
    assert n == 1
    status = conn.execute('SELECT status, lease_until FROM print_jobs').fetchone()
    assert status['status'] == 'pending'
    assert status['lease_until'] is None


def test_cleanup_old_jobs(conn):
    agent_id = _seed_agent(conn)
    drucker_id = _seed_printer(conn, agent_id=agent_id)
    old = (_utcnow() - timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
    fresh = _utcnow().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        '''INSERT INTO print_jobs (agent_id, drucker_id, zpl, status, completed_at, created_at)
           VALUES (?, ?, '^X', 'done', ?, ?)''',
        (agent_id, drucker_id, old, old),
    )
    conn.execute(
        '''INSERT INTO print_jobs (agent_id, drucker_id, zpl, status, completed_at, created_at)
           VALUES (?, ?, '^X', 'done', ?, ?)''',
        (agent_id, drucker_id, fresh, fresh),
    )
    conn.commit()
    n = cleanup_old_jobs(conn, retention_days=7)
    assert n == 1
    remaining = conn.execute('SELECT COUNT(*) AS n FROM print_jobs').fetchone()
    assert remaining['n'] == 1


def test_wait_for_job_returns_done_quickly(conn):
    agent_id = _seed_agent(conn)
    drucker_id = _seed_printer(conn, agent_id=agent_id)
    job_id = enqueue_print_job(conn, drucker_id, '^X')
    conn.execute(
        '''UPDATE print_jobs SET status = 'done', completed_at = datetime('now') WHERE id = ?''',
        (job_id,),
    )
    conn.commit()
    res = wait_for_job(conn, job_id, timeout=0.1)
    assert res['status'] == 'done'
