"""Tests for core/tool_state.py."""

from core.tool_state import ToolStateStore, ToolStatus


class TestToolStatus:
    def test_from_empty_dict_returns_defaults(self):
        status = ToolStatus.from_dict(None)
        assert status.installed is False
        assert status.source == "missing"


class TestToolStateStore:
    def test_update_and_reload_roundtrip(self, tmp_path):
        state_path = tmp_path / "tool_state.json"
        store = ToolStateStore(state_file=str(state_path))

        store.update(
            "mmseqs",
            installed=True,
            version="16-747c6",
            source="managed",
            executable_path="/tmp/mmseqs",
        )

        reloaded = ToolStateStore(state_file=str(state_path))
        status = reloaded.get("mmseqs")
        assert status.installed is True
        assert status.version == "16-747c6"
        assert status.source == "managed"
        assert status.executable_path == "/tmp/mmseqs"
        assert status.last_checked is not None
