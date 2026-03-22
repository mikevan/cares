"""
Application configuration.
Set APP_NAME and DEFAULT_ORGANIZATION here, or override using instance/config.py or environment variables.
"""
import os

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