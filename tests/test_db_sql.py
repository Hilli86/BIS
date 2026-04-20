"""Tests fuer ``utils.db_sql`` – dialektunabhaengige SQL-Helfer."""

from __future__ import annotations

import pytest

from utils.db_sql import (
    json_get,
    local_now_str,
    month_expr,
    now_sql,
    ph,
    resolve_dialect,
    string_agg,
    today_sql,
    upsert_ignore,
    upsert_replace,
    year_expr,
    year_month_expr,
)


class TestResolveDialect:
    def test_default_without_context_is_sqlite(self):
        assert resolve_dialect() == 'sqlite'

    def test_explicit_sqlite(self):
        assert resolve_dialect('sqlite') == 'sqlite'

    def test_explicit_postgresql(self):
        assert resolve_dialect('postgresql') == 'postgresql'

    def test_case_insensitive(self):
        assert resolve_dialect('PostgreSQL') == 'postgresql'
        assert resolve_dialect('SQLITE') == 'sqlite'

    def test_unknown_dialect_raises(self):
        with pytest.raises(ValueError):
            resolve_dialect('mysql')


class TestPh:
    def test_single_placeholder_sqlite(self):
        assert ph(dialect='sqlite') == '?'

    def test_single_placeholder_postgres(self):
        assert ph(dialect='postgresql') == '%s'

    def test_multiple_sqlite(self):
        assert ph(3, dialect='sqlite') == '?, ?, ?'

    def test_multiple_postgres(self):
        assert ph(4, dialect='postgresql') == '%s, %s, %s, %s'

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            ph(0)

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            ph(-1)

    def test_usable_in_in_clause(self):
        ids = [1, 2, 3]
        sql = f'SELECT ID FROM Mitarbeiter WHERE ID IN ({ph(len(ids), dialect="sqlite")})'
        assert sql == 'SELECT ID FROM Mitarbeiter WHERE ID IN (?, ?, ?)'


class TestUpsertIgnore:
    def test_sqlite(self):
        sql = upsert_ignore(
            'MitarbeiterAbteilung',
            ['MitarbeiterID', 'AbteilungID'],
            ['MitarbeiterID', 'AbteilungID'],
            dialect='sqlite',
        )
        assert sql == (
            'INSERT INTO MitarbeiterAbteilung (MitarbeiterID, AbteilungID) '
            'VALUES (?, ?) ON CONFLICT (MitarbeiterID, AbteilungID) DO NOTHING'
        )

    def test_postgresql_uses_percent_s(self):
        sql = upsert_ignore(
            't', ['a', 'b', 'c'], ['a'], dialect='postgresql'
        )
        assert sql == (
            'INSERT INTO t (a, b, c) VALUES (%s, %s, %s) '
            'ON CONFLICT (a) DO NOTHING'
        )

    def test_empty_columns_raises(self):
        with pytest.raises(ValueError):
            upsert_ignore('t', [], ['a'])

    def test_empty_conflict_cols_raises(self):
        with pytest.raises(ValueError):
            upsert_ignore('t', ['a'], [])


class TestUpsertReplace:
    def test_default_updates_all_non_conflict_cols(self):
        sql = upsert_replace(
            'Berechtigung',
            ['Schluessel', 'Bezeichnung', 'Beschreibung', 'Aktiv'],
            ['Schluessel'],
            dialect='sqlite',
        )
        assert sql == (
            'INSERT INTO Berechtigung '
            '(Schluessel, Bezeichnung, Beschreibung, Aktiv) '
            'VALUES (?, ?, ?, ?) '
            'ON CONFLICT (Schluessel) DO UPDATE SET '
            'Bezeichnung = excluded.Bezeichnung, '
            'Beschreibung = excluded.Beschreibung, '
            'Aktiv = excluded.Aktiv'
        )

    def test_explicit_update_cols(self):
        sql = upsert_replace(
            't',
            ['a', 'b', 'c'],
            ['a'],
            update_cols=['c'],
            dialect='sqlite',
        )
        assert sql == (
            'INSERT INTO t (a, b, c) VALUES (?, ?, ?) '
            'ON CONFLICT (a) DO UPDATE SET c = excluded.c'
        )

    def test_postgresql_placeholders(self):
        sql = upsert_replace(
            't', ['a', 'b'], ['a'], dialect='postgresql'
        )
        assert 'VALUES (%s, %s)' in sql
        assert 'DO UPDATE SET b = excluded.b' in sql

    def test_no_update_cols_raises(self):
        # Alle Spalten sind Konflikt-Spalten -> keine Update-Spalten mehr uebrig
        with pytest.raises(ValueError):
            upsert_replace('t', ['a', 'b'], ['a', 'b'])


class TestStringAgg:
    def test_sqlite_default_separator(self):
        assert string_agg('Bezeichnung', dialect='sqlite') == "GROUP_CONCAT(Bezeichnung, ', ')"

    def test_sqlite_custom_separator(self):
        assert string_agg('x', '|', dialect='sqlite') == "GROUP_CONCAT(x, '|')"

    def test_postgresql_default_separator(self):
        assert string_agg('Bezeichnung', dialect='postgresql') == (
            "STRING_AGG((Bezeichnung)::text, ', ')"
        )

    def test_postgresql_custom_separator(self):
        assert string_agg('x', ' / ', dialect='postgresql') == (
            "STRING_AGG((x)::text, ' / ')"
        )

    def test_separator_with_single_quote_is_escaped(self):
        assert string_agg('x', "'", dialect='sqlite') == "GROUP_CONCAT(x, '''')"


class TestNowSql:
    def test_sqlite(self):
        assert now_sql(dialect='sqlite') == 'CURRENT_TIMESTAMP'

    def test_postgresql(self):
        assert now_sql(dialect='postgresql') == 'NOW()'


class TestTodaySql:
    def test_sqlite(self):
        assert today_sql(dialect='sqlite') == "DATE('now')"

    def test_postgresql(self):
        assert today_sql(dialect='postgresql') == 'CURRENT_DATE'


class TestJsonGet:
    def test_sqlite(self):
        assert json_get('Zusatzdaten', 'foo', dialect='sqlite') == (
            "json_extract(Zusatzdaten, '$.foo')"
        )

    def test_postgresql(self):
        assert json_get('Zusatzdaten', 'foo', dialect='postgresql') == (
            "(Zusatzdaten)->>'foo'"
        )

    def test_sqlite_with_special_char_key(self):
        assert json_get('col', "a'b", dialect='sqlite') == (
            "json_extract(col, '$.a''b')"
        )

    def test_empty_key_raises(self):
        with pytest.raises(ValueError):
            json_get('col', '')


class TestMonthExpr:
    def test_sqlite(self):
        assert month_expr('d.DurchgefuehrtAm', dialect='sqlite') == (
            "CAST(strftime('%m', d.DurchgefuehrtAm) AS INTEGER)"
        )

    def test_postgresql(self):
        assert month_expr('d.DurchgefuehrtAm', dialect='postgresql') == (
            'CAST(EXTRACT(MONTH FROM d.DurchgefuehrtAm) AS INTEGER)'
        )


class TestYearExpr:
    def test_sqlite(self):
        assert year_expr('col', dialect='sqlite') == (
            "CAST(strftime('%Y', col) AS INTEGER)"
        )

    def test_postgresql(self):
        assert year_expr('col', dialect='postgresql') == (
            'CAST(EXTRACT(YEAR FROM col) AS INTEGER)'
        )


class TestYearMonthExpr:
    def test_sqlite(self):
        assert year_month_expr('b.BestelltAm', dialect='sqlite') == (
            "strftime('%Y-%m', b.BestelltAm)"
        )

    def test_postgresql(self):
        assert year_month_expr('b.BestelltAm', dialect='postgresql') == (
            "TO_CHAR(b.BestelltAm, 'YYYY-MM')"
        )


class TestLocalNowStr:
    def test_format_default(self):
        # Grobe Sanity: Laenge und Trennzeichen passen zum ISO-Default
        s = local_now_str()
        assert len(s) == 19
        assert s[4] == '-' and s[7] == '-' and s[10] == ' '
        assert s[13] == ':' and s[16] == ':'

    def test_custom_format(self):
        s = local_now_str('%Y%m%d')
        assert len(s) == 8
        assert s.isdigit()


class TestIntegrationSmokeSqlite:
    """Gegenprobe: rendert eine realistische Query und fuehrt sie gegen SQLite aus."""

    def test_upsert_ignore_runs(self):
        import sqlite3

        conn = sqlite3.connect(':memory:')
        conn.execute(
            'CREATE TABLE t (a INTEGER, b TEXT, PRIMARY KEY (a))'
        )
        sql = upsert_ignore('t', ['a', 'b'], ['a'], dialect='sqlite')
        conn.execute(sql, (1, 'x'))
        conn.execute(sql, (1, 'y'))  # Zweiter Insert wird ignoriert
        row = conn.execute('SELECT b FROM t WHERE a = 1').fetchone()
        assert row[0] == 'x'

    def test_upsert_replace_runs(self):
        import sqlite3

        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE t (a INTEGER PRIMARY KEY, b TEXT)')
        sql = upsert_replace('t', ['a', 'b'], ['a'], dialect='sqlite')
        conn.execute(sql, (1, 'x'))
        conn.execute(sql, (1, 'y'))
        row = conn.execute('SELECT b FROM t WHERE a = 1').fetchone()
        assert row[0] == 'y'

    def test_string_agg_runs(self):
        import sqlite3

        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE t (g INTEGER, v TEXT)')
        conn.executemany(
            'INSERT INTO t VALUES (?, ?)', [(1, 'a'), (1, 'b'), (1, 'c')]
        )
        agg = string_agg('v', '|', dialect='sqlite')
        row = conn.execute(f'SELECT {agg} FROM t GROUP BY g').fetchone()
        assert row[0] == 'a|b|c'

    def test_json_get_runs(self):
        import sqlite3

        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE t (data TEXT)')
        conn.execute("INSERT INTO t VALUES (?)", ('{"name":"bob","age":42}',))
        sql = f"SELECT {json_get('data', 'name', dialect='sqlite')} FROM t"
        row = conn.execute(sql).fetchone()
        assert row[0] == 'bob'
