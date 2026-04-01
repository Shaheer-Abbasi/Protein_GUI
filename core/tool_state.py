"""Persistent state for managed tool discovery and installs."""

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from typing import Dict


def _default_state_root() -> str:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(base, "SenLab", "ProteinGUI", "tools", "state")
    return os.path.join(os.path.expanduser("~"), ".senlab", "protein_gui", "tools", "state")


@dataclass
class ToolStatus:
    """Lightweight persisted status for a single tool."""

    installed: bool = False
    version: str | None = None
    source: str = "missing"
    executable_path: str | None = None
    last_checked: str | None = None
    error_message: str | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> "ToolStatus":
        if not data:
            return cls()
        return cls(**data)


class ToolStateStore:
    """JSON-backed store of the last known tool status values."""

    def __init__(self, state_file: str | None = None):
        self.state_file = state_file or os.path.join(_default_state_root(), "tool_state.json")
        self._state = self._load()

    def _load(self) -> Dict[str, ToolStatus]:
        if not os.path.exists(self.state_file):
            return {}
        try:
            with open(self.state_file, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            return {tool_id: ToolStatus.from_dict(data) for tool_id, data in raw.items()}
        except Exception:
            return {}

    def save(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        serializable = {tool_id: asdict(status) for tool_id, status in self._state.items()}
        with open(self.state_file, "w", encoding="utf-8") as handle:
            json.dump(serializable, handle, indent=2, sort_keys=True)

    def get(self, tool_id: str) -> ToolStatus:
        return self._state.get(tool_id, ToolStatus())

    def set(self, tool_id: str, status: ToolStatus):
        status.last_checked = status.last_checked or datetime.utcnow().isoformat()
        self._state[tool_id] = status
        self.save()

    def update(
        self,
        tool_id: str,
        *,
        installed: bool,
        version: str | None,
        source: str,
        executable_path: str | None,
        error_message: str | None = None,
    ):
        self.set(
            tool_id,
            ToolStatus(
                installed=installed,
                version=version,
                source=source,
                executable_path=executable_path,
                error_message=error_message,
                last_checked=datetime.utcnow().isoformat(),
            ),
        )


_tool_state_store: ToolStateStore | None = None


def get_tool_state_store() -> ToolStateStore:
    """Return the process-wide shared tool state store."""

    global _tool_state_store
    if _tool_state_store is None:
        _tool_state_store = ToolStateStore()
    return _tool_state_store
