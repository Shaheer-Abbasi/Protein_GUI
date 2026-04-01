"""Tests for core/micromamba_manager.py."""

from core.micromamba_manager import MicromambaManager


class TestMicromambaManager:
    def test_get_managed_executable_from_env_bin(self, tmp_path):
        manager = MicromambaManager(tools_root=str(tmp_path), env_name="bio-tools")
        bin_dir = tmp_path / "envs" / "bio-tools" / "bin"
        bin_dir.mkdir(parents=True)
        executable = bin_dir / "blastp"
        executable.write_text("")

        assert manager.get_managed_executable("blastp") == str(executable)

    def test_get_micromamba_executable_finds_nested_binary(self, tmp_path):
        manager = MicromambaManager(tools_root=str(tmp_path), env_name="bio-tools")
        binary = tmp_path / "micromamba" / "bin" / "micromamba"
        binary.parent.mkdir(parents=True)
        binary.write_text("")

        assert manager.get_micromamba_executable() == str(binary)

    def test_install_packages_with_empty_list_returns_env_path(self, tmp_path):
        manager = MicromambaManager(tools_root=str(tmp_path), env_name="bio-tools")
        assert manager.install_packages([]) == str(tmp_path / "envs" / "bio-tools")
