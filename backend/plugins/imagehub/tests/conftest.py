"""Shared app/client fixtures from the project ``tests/conftest.py``, which is not
a parent of this folder and must be imported explicitly."""
import pytest

from plugins.imagehub import config
from tests.conftest import *  # noqa: F401,F403


@pytest.fixture(autouse=True)
def _shipped_configs_only(monkeypatch):
    """Tests see the shipped example configs only, never datasets/local/: a test
    must not pass or fail because of someone's own dataset."""
    shipped = config.load_dir(config.DATASET_DIRS[0])
    monkeypatch.setattr(config, "datasets", lambda: shipped)
    monkeypatch.delenv("IMAGEHUB_DATASET", raising=False)
