"""Unit tests for sandbox-service executor.py — auto-start stopped containers.

These tests verify that exec_command, upload_files_to_container, and
download_file_bytes automatically start a stopped container before proceeding.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure sandbox-service is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sandbox-service"))

from executor import (
    _ensure_container_running,
    exec_command,
    upload_files_to_container,
    download_file_bytes,
)


# ---------------------------------------------------------------------------
# _ensure_container_running
# ---------------------------------------------------------------------------


class TestEnsureContainerRunning:
    """Tests for _ensure_container_running helper."""

    def test_running_container_returns_immediately(self):
        """If the container is already running, no start is attempted."""
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.reload = MagicMock()

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch("executor.get_docker_client", return_value=mock_client):
            container = _ensure_container_running("abc123")

        assert container is mock_container
        mock_container.reload.assert_called_once()
        assert not mock_container.start.called

    def test_stopped_container_is_started(self):
        """If the container is stopped, start_sandbox is called."""
        mock_container = MagicMock()
        mock_container.status = "exited"
        # First reload: stays exited. Second reload (after start): becomes running.
        reload_count = [0]
        def after_reload():
            reload_count[0] += 1
            if reload_count[0] >= 2:
                mock_container.status = "running"
        mock_container.reload.side_effect = after_reload

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch("executor.get_docker_client", return_value=mock_client):
            with patch("manager.start_sandbox") as mock_start:
                container = _ensure_container_running("abc123")

        mock_start.assert_called_once_with("abc123")
        assert container.status == "running"
        assert mock_container.reload.call_count == 2  # initial + after start

    def test_container_not_found_raises(self):
        """If the container does not exist, NotFound is propagated."""
        from docker.errors import NotFound

        mock_client = MagicMock()
        mock_client.containers.get.side_effect = NotFound("No such container")

        with patch("executor.get_docker_client", return_value=mock_client):
            with pytest.raises(NotFound):
                _ensure_container_running("missing-id")

    def test_container_fails_to_start_raises(self):
        """If start_sandbox succeeds but container still isn't running, raise."""
        mock_container = MagicMock()
        mock_container.status = "exited"
        mock_container.reload = MagicMock()
        # status stays "exited" even after start

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch("executor.get_docker_client", return_value=mock_client):
            with patch("manager.start_sandbox") as mock_start:
                with pytest.raises(RuntimeError) as exc_info:
                    _ensure_container_running("abc123")

        assert "did not start" in str(exc_info.value)
        mock_start.assert_called_once_with("abc123")


# ---------------------------------------------------------------------------
# exec_command
# ---------------------------------------------------------------------------


class TestExecCommandAutoStart:
    """Tests for exec_command with auto-start behavior."""

    def test_exec_on_running_container(self):
        """Normal exec on a running container — no start needed."""
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.labels = {"platform.session_id": "sess-123"}
        mock_container.reload = MagicMock()

        mock_exec_result = MagicMock()
        mock_exec_result.exit_code = 0
        mock_exec_result.output = b"hello\n"
        mock_container.exec_run.return_value = mock_exec_result

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch("executor.get_docker_client", return_value=mock_client):
            with patch("executor._report_exec") as mock_report:
                result = exec_command("abc123", "echo hello")

        assert result["output"] == "hello\n"
        assert result["exit_code"] == 0
        mock_container.exec_run.assert_called_once()
        mock_report.assert_called_once_with("sess-123", "abc123")

    def test_exec_auto_starts_stopped_container(self):
        """Exec on a stopped container triggers auto-start."""
        mock_container = MagicMock()
        mock_container.labels = {"platform.session_id": "sess-123"}
        mock_container.reload = MagicMock()

        # First reload: stopped, second reload: running (after start_sandbox)
        reload_count = [0]
        def reload_side_effect():
            reload_count[0] += 1
            if reload_count[0] >= 2:
                mock_container.status = "running"
        mock_container.reload.side_effect = reload_side_effect
        mock_container.status = "exited"

        mock_exec_result = MagicMock()
        mock_exec_result.exit_code = 0
        mock_exec_result.output = b"hello\n"
        mock_container.exec_run.return_value = mock_exec_result

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch("executor.get_docker_client", return_value=mock_client):
            with patch("manager.start_sandbox") as mock_start:
                with patch("executor._report_exec") as mock_report:
                    result = exec_command("abc123", "echo hello")

        mock_start.assert_called_once_with("abc123")
        assert result["output"] == "hello\n"
        mock_report.assert_called_once_with("sess-123", "abc123")

    def test_exec_container_destroyed_returns_error(self):
        """If container is destroyed, exec raises RuntimeError (propagated as 500)."""
        from docker.errors import NotFound

        mock_client = MagicMock()
        mock_client.containers.get.side_effect = NotFound("No such container")

        with patch("executor.get_docker_client", return_value=mock_client):
            with pytest.raises(NotFound):
                exec_command("abc123", "echo hello")


# ---------------------------------------------------------------------------
# upload_files_to_container
# ---------------------------------------------------------------------------


class TestUploadFilesAutoStart:
    """Tests for upload_files_to_container with auto-start behavior."""

    def test_upload_on_running_container(self):
        """Normal upload on a running container — no start needed."""
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.labels = {"platform.session_id": "sess-123"}
        mock_container.reload = MagicMock()

        # exec_run for mkdir returns success, then exec_run for write returns success
        def exec_run_side_effect(*args, **kwargs):
            result = MagicMock()
            result.exit_code = 0
            result.output = b""
            return result
        mock_container.exec_run.side_effect = exec_run_side_effect

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch("executor.get_docker_client", return_value=mock_client):
            with patch("executor._report_exec") as mock_report:
                results = upload_files_to_container("abc123", [("test.py", b"print('hi')")])

        assert len(results) == 1
        assert results[0]["error"] is None
        mock_report.assert_called_once_with("sess-123", "abc123")

    def test_upload_auto_starts_stopped_container(self):
        """Upload on a stopped container triggers auto-start."""
        mock_container = MagicMock()
        mock_container.labels = {"platform.session_id": "sess-123"}
        mock_container.reload = MagicMock()

        reload_count = [0]
        def reload_side_effect():
            reload_count[0] += 1
            if reload_count[0] >= 2:
                mock_container.status = "running"
        mock_container.reload.side_effect = reload_side_effect
        mock_container.status = "exited"

        def exec_run_side_effect(*args, **kwargs):
            result = MagicMock()
            result.exit_code = 0
            result.output = b""
            return result
        mock_container.exec_run.side_effect = exec_run_side_effect

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch("executor.get_docker_client", return_value=mock_client):
            with patch("manager.start_sandbox") as mock_start:
                with patch("executor._report_exec") as mock_report:
                    results = upload_files_to_container("abc123", [("test.py", b"print('hi')")])

        mock_start.assert_called_once_with("abc123")
        assert results[0]["error"] is None
        mock_report.assert_called_once_with("sess-123", "abc123")


# ---------------------------------------------------------------------------
# download_file_bytes
# ---------------------------------------------------------------------------


class TestDownloadFilesAutoStart:
    """Tests for download_file_bytes with auto-start behavior."""

    def test_download_on_running_container(self):
        """Normal download on a running container — no start needed."""
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.labels = {"platform.session_id": "sess-123"}
        mock_container.reload = MagicMock()

        mock_exec_result = MagicMock()
        mock_exec_result.exit_code = 0
        mock_exec_result.output = b"file contents"
        mock_container.exec_run.return_value = mock_exec_result

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch("executor.get_docker_client", return_value=mock_client):
            with patch("executor._report_exec") as mock_report:
                content = download_file_bytes("abc123", "test.py")

        assert content == b"file contents"
        mock_report.assert_called_once_with("sess-123", "abc123")

    def test_download_auto_starts_stopped_container(self):
        """Download on a stopped container triggers auto-start."""
        mock_container = MagicMock()
        mock_container.labels = {"platform.session_id": "sess-123"}
        mock_container.reload = MagicMock()

        reload_count = [0]
        def reload_side_effect():
            reload_count[0] += 1
            if reload_count[0] >= 2:
                mock_container.status = "running"
        mock_container.reload.side_effect = reload_side_effect
        mock_container.status = "exited"

        mock_exec_result = MagicMock()
        mock_exec_result.exit_code = 0
        mock_exec_result.output = b"file contents"
        mock_container.exec_run.return_value = mock_exec_result

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch("executor.get_docker_client", return_value=mock_client):
            with patch("manager.start_sandbox") as mock_start:
                with patch("executor._report_exec") as mock_report:
                    content = download_file_bytes("abc123", "test.py")

        mock_start.assert_called_once_with("abc123")
        assert content == b"file contents"
        mock_report.assert_called_once_with("sess-123", "abc123")

    def test_download_file_not_found(self):
        """If the file doesn't exist, FileNotFoundError is raised even after auto-start."""
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.labels = {"platform.session_id": "sess-123"}
        mock_container.reload = MagicMock()

        mock_exec_result = MagicMock()
        mock_exec_result.exit_code = 1
        mock_exec_result.output = b""
        mock_container.exec_run.return_value = mock_exec_result

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch("executor.get_docker_client", return_value=mock_client):
            with patch("executor._report_exec"):
                with pytest.raises(FileNotFoundError) as exc_info:
                    download_file_bytes("abc123", "nonexistent.py")

        assert "File not found" in str(exc_info.value)


# ---------------------------------------------------------------------------
# start_sandbox idempotency
# ---------------------------------------------------------------------------


class TestStartSandboxIdempotency:
    """Tests for the start_sandbox early-return guard in manager.py."""

    def test_start_sandbox_already_running_returns_early(self):
        """If the container is already running, start_sandbox returns without calling start()."""
        import manager

        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.reload = MagicMock()

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch("manager.get_docker_client", return_value=mock_client):
            manager.start_sandbox("abc123")

        mock_container.reload.assert_called_once()
        assert not mock_container.start.called

    def test_start_sandbox_stopped_triggers_start(self):
        """If the container is stopped, start_sandbox calls container.start()."""
        import manager

        mock_container = MagicMock()
        mock_container.status = "exited"
        mock_container.reload = MagicMock()
        mock_container.labels = {"platform.environment_id": "env-123"}

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch("manager.get_docker_client", return_value=mock_client):
            manager.start_sandbox("abc123")

        mock_container.start.assert_called_once()
