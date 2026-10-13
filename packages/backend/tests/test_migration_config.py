"""Migration configuration must parse under both CI and Windows locales."""
import configparser
from pathlib import Path

import pytest


@pytest.mark.parametrize("encoding", ["utf-8", "gbk"])
def test_alembic_configuration_can_be_read_in_supported_locales(encoding):
    path = Path(__file__).parents[1] / "alembic.ini"
    config = configparser.ConfigParser()
    assert config.read(path, encoding=encoding) == [str(path)]
    assert config.get("alembic", "script_location", raw=True) == "%(here)s/app/migrations"
    assert config.has_section("loggers")
