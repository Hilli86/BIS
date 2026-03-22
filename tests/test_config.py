"""Konstanten und Konfigurationsklasse (ohne Produktions-Import von app)."""

from config import DEV_SECRET_KEY_FALLBACK, DevelopmentConfig, ProductionConfig


def test_dev_secret_fallback_is_non_trivial():
    assert isinstance(DEV_SECRET_KEY_FALLBACK, str)
    assert len(DEV_SECRET_KEY_FALLBACK) >= 16


def test_development_config_enables_debug():
    assert DevelopmentConfig.DEBUG is True


def test_production_config_disables_debug():
    assert ProductionConfig.DEBUG is False
