"""Tests für utils.file_handling (benötigt Flask-App-Kontext für Config)."""

from app import app
from utils.file_handling import validate_file_extension


def test_validate_file_extension_pdf_and_exe():
    with app.app_context():
        assert validate_file_extension("Dokument.pdf") is True
        assert validate_file_extension("datei.PDF") is True
        assert validate_file_extension("trojan.exe") is False
        assert validate_file_extension("") is False


def test_validate_file_extension_explicit_allowlist():
    with app.app_context():
        assert validate_file_extension("a.txt", {"txt", "md"}) is True
        assert validate_file_extension("a.exe", {"txt"}) is False
