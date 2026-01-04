"""Common test fixtures."""

import pytest
from pathlib import Path

from fasthooks.testing import MockEvent


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Empty project directory."""
    return tmp_path


@pytest.fixture
def mock_event() -> type[MockEvent]:
    """MockEvent factory class."""
    return MockEvent
