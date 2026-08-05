"""Focused MySQL gate settings for database-specific accountant portal tests."""
import os

from core.settings import *  # noqa: F403


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("MYSQL_DATABASE", "ktra"),
        "USER": os.environ.get("MYSQL_USER", "root"),
        "PASSWORD": os.environ.get("MYSQL_PASSWORD", ""),
        "HOST": os.environ.get("MYSQL_HOST", "localhost"),
        "PORT": os.environ.get("MYSQL_PORT", "3306"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": (
                "SET foreign_key_checks = 0; "
                "SET sql_mode='STRICT_TRANS_TABLES', innodb_strict_mode=1;"
            ),
            "connect_timeout": 10,
            "read_timeout": 30,
            "write_timeout": 30,
        },
        "TEST": {"NAME": "test_ktra_accountant_gate"},
    }
}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}


class _DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = _DisableMigrations()
