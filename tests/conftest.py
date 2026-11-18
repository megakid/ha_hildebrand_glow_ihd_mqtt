"""Shared fixtures for the Hildebrand Glow IHD MQTT tests."""
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent

# The integration's folder is named hildebrand_glow_ihd_mqtt but its domain is
# hildebrand_glow_ihd (HACS installs it under the domain name). Home Assistant
# loads integrations by folder name, so expose the code under the domain name.
_LINK_ROOT = Path(tempfile.mkdtemp(prefix="glow-ihd-tests-"))
(_LINK_ROOT / "custom_components").mkdir()
(_LINK_ROOT / "custom_components" / "hildebrand_glow_ihd").symlink_to(
    _REPO / "custom_components" / "hildebrand_glow_ihd_mqtt",
    target_is_directory=True,
)
sys.path.insert(0, str(_LINK_ROOT))

import custom_components  # noqa: E402

# pytest-homeassistant-custom-component ships its own `custom_components`
# package, so extend its search path instead of relying on namespace merging.
for _path in (_LINK_ROOT / "custom_components", _REPO / "custom_components"):
    if str(_path) not in custom_components.__path__:
        custom_components.__path__.append(str(_path))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the integration in every test."""
    yield


@pytest.fixture
def expected_lingering_timers() -> bool:
    """Home Assistant's MQTT client keeps a periodic timer alive after a test."""
    return True
