"""Tests fuer utils.auth_guards (Session-Pruefungen)."""

from utils.auth_guards import (
    is_authenticated_or_guest,
    is_authenticated_user,
    is_guest,
)


def test_is_authenticated_user_echter_nutzer():
    assert is_authenticated_user({"user_id": 42}) is True


def test_is_authenticated_user_gast_ist_kein_nutzer():
    assert is_authenticated_user({"user_id": 42, "is_guest": True}) is False
    # Gast-Logins setzen user_id=None, is_guest=True
    assert is_authenticated_user({"user_id": None, "is_guest": True}) is False


def test_is_authenticated_user_leere_session():
    assert is_authenticated_user({}) is False


def test_is_authenticated_user_user_id_none():
    assert is_authenticated_user({"user_id": None}) is False


def test_is_guest_nur_bei_gast_flag():
    assert is_guest({"is_guest": True}) is True
    assert is_guest({"is_guest": False}) is False
    assert is_guest({}) is False
    assert is_guest({"user_id": 1}) is False


def test_is_authenticated_or_guest():
    assert is_authenticated_or_guest({"user_id": 1}) is True
    assert is_authenticated_or_guest({"is_guest": True}) is True
    assert is_authenticated_or_guest({"user_id": None, "is_guest": True}) is True
    assert is_authenticated_or_guest({}) is False
    assert is_authenticated_or_guest({"user_id": None}) is False
