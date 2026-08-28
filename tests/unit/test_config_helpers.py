"""
CARES Test Harness - Unit Tests - Config Helpers
==================================================

Unit tests for config.py's environment-resolution helpers (no Flask app,
no database -- these are plain functions operating on os.environ).

Covers the §4 auth-hardening fix: SECRET_KEY/DATABASE_URL must fail loudly
in production instead of silently falling back to a well-known default.
"""

import pytest

from config import is_production, resolve_secret, parse_bool_env


@pytest.mark.unit
class TestIsProduction:
    def test_true_when_flask_env_is_production(self, monkeypatch):
        monkeypatch.setenv('FLASK_ENV', 'production')
        assert is_production() is True

    def test_true_when_flask_env_is_production_any_case(self, monkeypatch):
        monkeypatch.setenv('FLASK_ENV', 'Production')
        assert is_production() is True

    def test_false_when_flask_env_is_development(self, monkeypatch):
        monkeypatch.setenv('FLASK_ENV', 'development')
        assert is_production() is False

    def test_false_when_flask_env_is_unset(self, monkeypatch):
        monkeypatch.delenv('FLASK_ENV', raising=False)
        assert is_production() is False


@pytest.mark.unit
class TestResolveSecret:
    def test_uses_environment_value_when_set(self, monkeypatch):
        monkeypatch.setenv('SOME_SECRET', 'real-value-from-env')
        assert resolve_secret('SOME_SECRET', 'dev-default', production=True) == 'real-value-from-env'
        assert resolve_secret('SOME_SECRET', 'dev-default', production=False) == 'real-value-from-env'

    def test_falls_back_to_dev_default_outside_production(self, monkeypatch):
        monkeypatch.delenv('SOME_SECRET', raising=False)
        assert resolve_secret('SOME_SECRET', 'dev-default', production=False) == 'dev-default'

    def test_raises_in_production_when_missing(self, monkeypatch):
        monkeypatch.delenv('SOME_SECRET', raising=False)
        with pytest.raises(RuntimeError, match='SOME_SECRET'):
            resolve_secret('SOME_SECRET', 'dev-default', production=True)

    def test_empty_string_is_treated_as_missing(self, monkeypatch):
        """An accidentally-blank env var (e.g. SECRET_KEY= with nothing after
        it) must not silently pass through as a real secret."""
        monkeypatch.setenv('SOME_SECRET', '')
        with pytest.raises(RuntimeError):
            resolve_secret('SOME_SECRET', 'dev-default', production=True)
        assert resolve_secret('SOME_SECRET', 'dev-default', production=False) == 'dev-default'

    def test_production_is_inferred_from_flask_env_when_not_passed(self, monkeypatch):
        monkeypatch.delenv('SOME_SECRET', raising=False)
        monkeypatch.setenv('FLASK_ENV', 'production')
        with pytest.raises(RuntimeError):
            resolve_secret('SOME_SECRET', 'dev-default')

        monkeypatch.setenv('FLASK_ENV', 'development')
        assert resolve_secret('SOME_SECRET', 'dev-default') == 'dev-default'


@pytest.mark.unit
class TestParseBoolEnv:
    @pytest.mark.parametrize('value', ['1', 'true', 'True', 'TRUE', 'yes', 'Yes', 'on', 'ON'])
    def test_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv('SOME_FLAG', value)
        assert parse_bool_env('SOME_FLAG') is True

    @pytest.mark.parametrize('value', ['0', 'false', 'False', 'no', 'off', 'garbage', ''])
    def test_falsy_values(self, monkeypatch, value):
        monkeypatch.setenv('SOME_FLAG', value)
        assert parse_bool_env('SOME_FLAG') is False

    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv('SOME_FLAG', raising=False)
        assert parse_bool_env('SOME_FLAG') is False
        assert parse_bool_env('SOME_FLAG', default=True) is True
