"""Tests for core/tool_runtime.py."""

import importlib

import core.config_manager as config_manager
import core.tool_runtime as tool_runtime_module


def _fresh_runtime(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")
    config_manager._config_instance = config_manager.ConfigManager(config_path=str(config_path))
    tool_runtime_module._tool_runtime = None
    return tool_runtime_module.get_tool_runtime()


class TestToolRuntime:
    def test_resolve_tool_prefers_managed_source(self, tmp_path, monkeypatch):
        runtime = _fresh_runtime(tmp_path)

        monkeypatch.setattr(runtime.manager, "get_managed_executable", lambda name: f"/managed/{name}")
        monkeypatch.setattr(tool_runtime_module.shutil, "which", lambda name: f"/usr/bin/{name}")

        resolution = runtime.resolve_tool("blastp")
        assert resolution.source == "managed"
        assert resolution.executable == "/managed/blastp"

    def test_resolve_tool_honors_source_override(self, tmp_path, monkeypatch):
        runtime = _fresh_runtime(tmp_path)
        runtime.config.set("tool_source_overrides", {"blastp": "system"})

        monkeypatch.setattr(runtime.manager, "get_managed_executable", lambda name: f"/managed/{name}")
        monkeypatch.setattr(tool_runtime_module.shutil, "which", lambda name: f"/usr/bin/{name}")

        resolution = runtime.resolve_tool("blastp")
        assert resolution.source == "system"
        assert resolution.executable == "/usr/bin/blastp"

    def test_get_missing_tools_for_feature(self, tmp_path, monkeypatch):
        runtime = _fresh_runtime(tmp_path)
        monkeypatch.setattr(runtime, "is_tool_available", lambda tool_id: tool_id == "blastdbcmd")

        missing = runtime.get_missing_tools_for_feature("protein_mmseqs")
        assert missing == ["mmseqs"]

    def test_install_tools_raises_when_platform_has_no_managed_support(self, tmp_path, monkeypatch):
        runtime = _fresh_runtime(tmp_path)
        monkeypatch.setattr(tool_runtime_module, "is_managed_install_supported", lambda tool_id: False)

        try:
            runtime.install_tools(["mmseqs"])
        except tool_runtime_module.ToolRuntimeError as exc:
            assert "not available" in str(exc)
        else:
            raise AssertionError("Expected ToolRuntimeError for unsupported managed install")
