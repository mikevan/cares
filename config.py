"""
Application configuration.
Set APP_NAME and DEFAULT_ORGANIZATION here, or override using instance/config.py or environment variables.
"""
import os


def is_production():
    """True only when FLASK_ENV is explicitly set to 'production'.

    This matches DEPLOY.md/RENDER_DEPLOYMENT_GUIDE.md, which both already
    instruct setting FLASK_ENV=production alongside SECRET_KEY and
    DATABASE_URL for a real deployment. Everything else (unset, or
    'development', as every local start.bat/.sh and migrate_and_start.bat/.sh
    script sets) is treated as local/dev and keeps today's friendly
    fallback defaults -- so this is opt-in strictness, not a change to any
    existing local workflow.
    """
    return os.environ.get('FLASK_ENV', '').strip().lower() == 'production'


def resolve_secret(env_var, dev_default, production=None):
    """Read a required-in-production setting from the environment.

    Returns the environment variable's value if set. Outside production,
    falls back to `dev_default` (today's behavior, unchanged). In
    production, a missing value raises RuntimeError instead of silently
    running with a well-known default -- e.g. a SECRET_KEY that breaks
    session/CSRF signing security, or a DATABASE_URL that points at
    someone's laptop.
    """
    if production is None:
        production = is_production()
    value = os.environ.get(env_var)
    if value:
        return value
    if production:
        raise RuntimeError(
            f"{env_var} environment variable is not set. Refusing to start "
            f"with an insecure default in production (FLASK_ENV=production). "
            f"Set {env_var} in the environment, or unset FLASK_ENV / set it "
            f"to 'development' for local use."
        )
    return dev_default


def parse_bool_env(env_var, default=False):
    """Read a boolean feature flag from the environment (e.g. ENABLE_TRANSLATION).

    Accepts '1', 'true', 'yes', 'on' (case-insensitive) as true; anything
    else, or an unset variable, resolves to `default`.
    """
    value = os.environ.get(env_var)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _read_version():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    version_file = os.path.join(base_dir, 'VERSION')
    try:
        with open(version_file, 'r') as f:
            # return f.read().strip() Commented out to avoid error when VERSION file is missing
            return f.read().strip().lstrip('\ufeff')
    except FileNotFoundError:
        return 'unknown'

class Config:
    # The visible application name shown in templates and generated reports
    APP_NAME = "CARES"

    # Default organization name used as report fallback and initial seed data
    DEFAULT_ORGANIZATION = "Example Organization"

    # Application version read from VERSION file in repo root
    APP_VERSION = _read_version()