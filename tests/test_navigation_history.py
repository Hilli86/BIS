"""Tests fuer reine Helfer in utils.navigation_history (ohne DB, ohne Session)."""

from utils.navigation_history import (
    MAX_STACK_ENTRIES,
    _is_editor_or_neu_endpoint,
    _label_for_endpoint,
    _path_canonical_key,
    _paths_equal,
    _short_label,
    _virtual_stack_for_current,
    current_full_path,
)


class _ReqStub:
    """Minimaler Request-Stub mit path + query_string."""

    def __init__(self, path="/", query_string=b""):
        self.path = path
        self.query_string = query_string


# ---------------------------------------------------------------------------
# current_full_path
# ---------------------------------------------------------------------------


def test_current_full_path_ohne_query():
    assert current_full_path(_ReqStub("/dashboard", b"")) == "/dashboard"


def test_current_full_path_mit_query():
    assert current_full_path(_ReqStub("/such", b"q=abc&p=1")) == "/such?q=abc&p=1"


def test_current_full_path_nicht_absoluter_pfad_wird_auf_slash_gesetzt():
    assert current_full_path(_ReqStub("oops", b"")) == "/"


# ---------------------------------------------------------------------------
# _paths_equal / _path_canonical_key
# ---------------------------------------------------------------------------


def test_paths_equal_query_reihenfolge_egal():
    assert _paths_equal("/x?a=1&b=2", "/x?b=2&a=1") is True


def test_paths_equal_trailing_slash_ignoriert():
    assert _paths_equal("/x/", "/x") is True


def test_paths_equal_unterschiedliche_pfade():
    assert _paths_equal("/x", "/y") is False


def test_paths_equal_keine_pfade():
    assert _paths_equal(None, None) is True
    assert _paths_equal("", "/x") is False


def test_path_canonical_key_lehnt_unsichere_pfade_ab():
    assert _path_canonical_key("//evil.example/x") == ("", "")
    assert _path_canonical_key("http://evil/") == ("", "")
    assert _path_canonical_key(None) == ("", "")


# ---------------------------------------------------------------------------
# _label_for_endpoint / _short_label
# ---------------------------------------------------------------------------


def test_label_for_endpoint_mapping_treffer():
    assert _label_for_endpoint("dashboard.dashboard") == "Dashboard"


def test_label_for_endpoint_fallback_aus_endpunktname():
    assert _label_for_endpoint("xyz.mein_test_endpunkt") == "Mein test endpunkt"


def test_label_for_endpoint_none_und_leer():
    assert _label_for_endpoint(None) == "Seite"
    assert _label_for_endpoint("") == "Seite"


def test_short_label_kuerzt_lange_strings():
    text = "a" * 60
    gekuerzt = _short_label(text)
    assert gekuerzt.endswith("...")
    # Kuerzung auf max_len-1 Zeichen + "..." -> deutlich kuerzer als das Original
    assert len(gekuerzt) < len(text)
    assert len(gekuerzt) <= 42


def test_short_label_unveraendert_wenn_kurz():
    assert _short_label("Kurz") == "Kurz"


# ---------------------------------------------------------------------------
# _is_editor_or_neu_endpoint
# ---------------------------------------------------------------------------


def test_is_editor_or_neu_endpoint_neu_und_bearbeiten():
    assert _is_editor_or_neu_endpoint("schichtbuch.thema_neu") is True
    assert _is_editor_or_neu_endpoint("ersatzteile.ersatzteil_bearbeiten") is True


def test_is_editor_or_neu_endpoint_zusatzliste():
    assert _is_editor_or_neu_endpoint("schichtbuch.themaneu") is True
    assert _is_editor_or_neu_endpoint("wartungen.durchfuehrung_mehrere") is True


def test_is_editor_or_neu_endpoint_normale_liste_ist_false():
    assert _is_editor_or_neu_endpoint("schichtbuch.themaliste") is False
    assert _is_editor_or_neu_endpoint(None) is False
    assert _is_editor_or_neu_endpoint("") is False


# ---------------------------------------------------------------------------
# _virtual_stack_for_current
# ---------------------------------------------------------------------------


def test_virtual_stack_append_bei_leerem_stack():
    virt = _virtual_stack_for_current([], "/dashboard", "dashboard.dashboard")
    assert len(virt) == 1
    assert virt[0]["path"] == "/dashboard"


def test_virtual_stack_dedup_wenn_top_gleich():
    stack = [{"path": "/dashboard", "endpoint": "dashboard.dashboard", "title": None}]
    virt = _virtual_stack_for_current(stack, "/dashboard", "dashboard.dashboard")
    assert len(virt) == 1


def test_virtual_stack_append_wenn_andere_seite():
    stack = [{"path": "/schichtbuch", "endpoint": "schichtbuch.themaliste", "title": None}]
    virt = _virtual_stack_for_current(stack, "/dashboard", "dashboard.dashboard")
    assert [e["path"] for e in virt] == ["/schichtbuch", "/dashboard"]


def test_virtual_stack_editor_endpoint_wird_nicht_angehaengt():
    stack = [{"path": "/x", "endpoint": "x.liste", "title": None}]
    virt = _virtual_stack_for_current(stack, "/x/neu", "x.thema_neu")
    assert virt == stack


def test_virtual_stack_trunkiert_auf_max_entries():
    stack = [
        {"path": f"/p{i}", "endpoint": f"mod.p{i}", "title": None}
        for i in range(MAX_STACK_ENTRIES)
    ]
    virt = _virtual_stack_for_current(stack, "/neu", "mod.neu_seite")
    assert len(virt) == MAX_STACK_ENTRIES
    assert virt[-1]["path"] == "/neu"
    assert virt[0]["path"] == "/p1"


def test_virtual_stack_ignoriert_ungueltigen_cur():
    stack = [{"path": "/x", "endpoint": "x.liste", "title": None}]
    virt = _virtual_stack_for_current(stack, "oops", "x.liste")
    assert virt == stack
