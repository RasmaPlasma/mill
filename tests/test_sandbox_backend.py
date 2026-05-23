"""Unit tests for DockerSandboxBackend — BaseSandbox implementation.

Tests all 4 abstract methods plus error handling. Uses mock httpx responses
(no real Docker or sandbox-service needed).
"""

import base64
from unittest.mock import MagicMock

import httpx

from sandbox.backend import DockerSandboxBackend, LazyDockerSandboxBackend


def _mock_response(status_code: int = 200, json_data: dict | None = None, content: bytes = b"") -> httpx.Response:
    """Build a mock httpx.Response."""
    resp = httpx.Response(
        status_code=status_code,
        json=json_data or {},
        content=content,
        request=httpx.Request("POST", "http://test"),
    )
    return resp


class TestDockerSandboxBackendId:
    """Tests for the id property."""

    def test_id_returns_container_id(self):
        backend = DockerSandboxBackend("abc123def456", "http://sandbox:8090")
        assert backend.id == "abc123def456"

    def test_id_returns_full_hex(self):
        long_id = "a" * 64
        backend = DockerSandboxBackend(long_id, "http://sandbox:8090")
        assert backend.id == long_id


class TestDockerSandboxBackendExecute:
    """Tests for execute()."""

    def test_execute_success(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "output": "hello world\n",
            "exit_code": 0,
            "truncated": False,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        backend._client = mock_client

        result = backend.execute("echo hello world")

        assert result.output == "hello world\n"
        assert result.exit_code == 0
        assert result.truncated is False
        mock_client.post.assert_called_once_with(
            "/sandboxes/abc123/exec",
            json={"command": "echo hello world"},
        )

    def test_execute_with_timeout(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"output": "", "exit_code": 0, "truncated": False}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        backend._client = mock_client

        result = backend.execute("sleep 1", timeout=5)

        mock_client.post.assert_called_once_with(
            "/sandboxes/abc123/exec",
            json={"command": "sleep 1", "timeout": 5},
        )
        assert result.exit_code == 0

    def test_execute_nonzero_exit(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "output": "command not found\n",
            "exit_code": 127,
            "truncated": False,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        backend._client = mock_client

        result = backend.execute("nonexistent_command")

        assert result.exit_code == 127
        assert "command not found" in result.output

    def test_execute_truncated_output(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "output": "x" * 100,
            "exit_code": 0,
            "truncated": True,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        backend._client = mock_client

        result = backend.execute("generate_output")

        assert result.truncated is True

    def test_execute_http_error_returns_error_response(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_resp = httpx.Response(
            status_code=500,
            content=b"Internal Server Error",
            request=httpx.Request("POST", "http://test"),
        )
        http_err = httpx.HTTPStatusError("500", request=mock_resp.request, response=mock_resp)
        mock_resp.raise_for_status = MagicMock(side_effect=http_err)
        mock_client.post.return_value = mock_resp
        backend._client = mock_client

        result = backend.execute("echo test")

        assert result.exit_code == 1
        assert "500" in result.output

    def test_execute_connection_error_returns_error_response(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        backend._client = mock_client

        result = backend.execute("echo test")

        assert result.exit_code == 1
        assert "connection error" in result.output.lower()


class TestDockerSandboxBackendUploadFiles:
    """Tests for upload_files()."""

    def test_upload_single_file(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"path": "test.py", "error": None}]
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        backend._client = mock_client

        content = b"print('hello')"
        results = backend.upload_files([("test.py", content)])

        assert len(results) == 1
        assert results[0].path == "test.py"
        assert results[0].error is None

        # Verify the content was base64-encoded
        call_args = mock_client.post.call_args
        files_data = call_args[1]["json"]["files"]
        assert files_data[0]["path"] == "test.py"
        assert files_data[0]["content"] == base64.b64encode(content).decode("ascii")

    def test_upload_absolute_workspace_path_normalized(self):
        """Absolute /workspace/ paths must be normalized to relative for the sandbox-service."""
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"path": "counter.json", "error": None}]
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        backend._client = mock_client

        results = backend.upload_files([("/workspace/counter.json", b'{"count": 1}')])

        assert len(results) == 1
        assert results[0].error is None

        call_args = mock_client.post.call_args
        files_data = call_args[1]["json"]["files"]
        assert files_data[0]["path"] == "counter.json"

    def test_upload_multiple_files(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"path": "a.py", "error": None},
            {"path": "b.py", "error": None},
        ]
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        backend._client = mock_client

        results = backend.upload_files([
            ("a.py", b"a"),
            ("b.py", b"b"),
        ])

        assert len(results) == 2
        assert all(r.error is None for r in results)

    def test_upload_partial_failure(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"path": "good.py", "error": None},
            {"path": "bad.py", "error": "permission_denied"},
        ]
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        backend._client = mock_client

        results = backend.upload_files([
            ("good.py", b"ok"),
            ("bad.py", b"fail"),
        ])

        assert results[0].error is None
        assert results[1].error == "permission_denied"

    def test_upload_connection_error_returns_error_per_file(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        backend._client = mock_client

        results = backend.upload_files([
            ("a.py", b"a"),
            ("b.py", b"b"),
        ])

        assert len(results) == 2
        assert all(r.error is not None for r in results)
        assert "Upload failed" in results[0].error


class TestDockerSandboxBackendDownloadFiles:
    """Tests for download_files()."""

    def test_download_single_file(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"file contents"
        mock_resp.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_resp
        backend._client = mock_client

        results = backend.download_files(["test.py"])

        assert len(results) == 1
        assert results[0].path == "test.py"
        assert results[0].content == b"file contents"
        assert results[0].error is None

    def test_download_absolute_workspace_path_normalized(self):
        """Absolute /workspace/ paths must be normalized to relative in the GET URL."""
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"file contents"
        mock_resp.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_resp
        backend._client = mock_client

        results = backend.download_files(["/workspace/counter.json"])

        assert len(results) == 1
        assert results[0].error is None
        assert results[0].content == b"file contents"

        # Verify the URL uses the relative path (no /workspace/ prefix)
        mock_client.get.assert_called_once_with(
            "/sandboxes/abc123/files/counter.json",
        )

    def test_download_file_not_found(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_resp = httpx.Response(
            status_code=404,
            content=b"Not Found",
            request=httpx.Request("GET", "http://test"),
        )
        http_err = httpx.HTTPStatusError("404", request=mock_resp.request, response=mock_resp)

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_resp.raise_for_status = MagicMock(side_effect=http_err)
        backend._client = mock_client

        results = backend.download_files(["nonexistent.py"])

        assert len(results) == 1
        assert results[0].error == "file_not_found"

    def test_download_multiple_files_mixed(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        # First call succeeds, second fails
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.content = b"ok"
        ok_resp.raise_for_status = MagicMock()

        err_resp = httpx.Response(
            status_code=404,
            content=b"Not Found",
            request=httpx.Request("GET", "http://test"),
        )
        http_err = httpx.HTTPStatusError("404", request=err_resp.request, response=err_resp)
        err_resp.raise_for_status = MagicMock(side_effect=http_err)

        mock_client = MagicMock()
        mock_client.get.side_effect = [ok_resp, err_resp]
        backend._client = mock_client

        results = backend.download_files(["exists.py", "missing.py"])

        assert len(results) == 2
        assert results[0].content == b"ok"
        assert results[0].error is None
        assert results[1].error == "file_not_found"

    def test_download_connection_error(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090")

        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        backend._client = mock_client

        results = backend.download_files(["test.py"])

        assert len(results) == 1
        assert results[0].error is not None
        assert "Download failed" in results[0].error


class TestDockerSandboxBackendAuth:
    """Tests for auth header configuration."""

    def test_auth_header_set_when_key_provided(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090", api_key="secret-key")
        assert backend._client.headers["Authorization"] == "Bearer secret-key"

    def test_no_auth_header_when_key_none(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090", api_key=None)
        assert "Authorization" not in backend._client.headers

    def test_no_auth_header_when_key_empty(self):
        backend = DockerSandboxBackend("abc123", "http://sandbox:8090", api_key="")
        assert "Authorization" not in backend._client.headers


class TestLazyDockerSandboxBackend:
    """Tests for LazyDockerSandboxBackend — lazy container creation."""

    def test_lazy_creation_on_first_execute(self):
        """Container is created on the first execute() call."""
        backend = LazyDockerSandboxBackend(
            session_id="sess-123",
            environment_id="env-123",
            agent_id="agent-123",
            packages={"pip": ["requests"]},
            resource_limits={"memory": "1g"},
            repositories=[],
            repo_secrets={},
            skill_repos=[],
            ip_subnet=None,
            base_image=None,
            sandbox_service_url="http://sandbox:8090",
            api_key=None,
            platform_url="http://localhost:2026",
        )

        lazy_mock = MagicMock()
        create_resp = MagicMock()
        create_resp.status_code = 201
        create_resp.json.return_value = {"container_id": "new-container-abc", "status": "running"}
        create_resp.raise_for_status = MagicMock()

        platform_resp = MagicMock()
        platform_resp.status_code = 204
        platform_resp.raise_for_status = MagicMock()

        lazy_mock.post.side_effect = [create_resp, platform_resp]
        backend._client = lazy_mock

        backend._ensure_backend()

        inner_mock = MagicMock()
        exec_resp = MagicMock()
        exec_resp.status_code = 200
        exec_resp.json.return_value = {"output": "hello\n", "exit_code": 0, "truncated": False}
        exec_resp.raise_for_status = MagicMock()
        inner_mock.post.return_value = exec_resp
        backend._backend._client = inner_mock

        result = backend.execute("echo hello")

        assert result.exit_code == 0
        assert result.output == "hello\n"
        assert lazy_mock.post.call_count >= 1
        first_call_url = lazy_mock.post.call_args_list[0][0][0]
        assert first_call_url == "/sandboxes"

    def test_concurrent_calls_only_one_creation(self):
        """Two threads racing call execute() — only one creates the container."""
        import threading
        import time

        backend = LazyDockerSandboxBackend(
            session_id="sess-123",
            environment_id="env-123",
            agent_id="agent-123",
            packages={},
            resource_limits={},
            repositories=[],
            repo_secrets={},
            skill_repos=[],
            ip_subnet=None,
            base_image=None,
            sandbox_service_url="http://sandbox:8090",
            api_key=None,
            platform_url="http://localhost:2026",
        )

        call_count = [0]

        def slow_post(*args, **kwargs):
            call_count[0] += 1
            time.sleep(0.05)
            resp = MagicMock()
            resp.status_code = 201
            resp.json.return_value = {"container_id": "race-container", "status": "running"}
            resp.raise_for_status = MagicMock()
            return resp

        def platform_post(*args, **kwargs):
            resp = MagicMock()
            resp.status_code = 204
            resp.raise_for_status = MagicMock()
            return resp

        lazy_mock = MagicMock()
        lazy_mock.post.side_effect = lambda *args, **kwargs: (
            slow_post(*args, **kwargs)
            if args[0] == "/sandboxes"
            else platform_post(*args, **kwargs)
        )
        backend._client = lazy_mock

        results = []

        def run():
            backend._ensure_backend()
            inner_mock = MagicMock()
            exec_resp = MagicMock()
            exec_resp.status_code = 200
            exec_resp.json.return_value = {"output": "ok\n", "exit_code": 0, "truncated": False}
            exec_resp.raise_for_status = MagicMock()
            inner_mock.post.return_value = exec_resp
            backend._backend._client = inner_mock
            r = backend.execute("echo ok")
            results.append(r)

        t1 = threading.Thread(target=run)
        t2 = threading.Thread(target=run)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(results) == 2
        assert all(r.exit_code == 0 for r in results)
        assert call_count[0] == 1

    def test_creation_error_returns_error_response(self):
        """If sandbox creation fails, the tool call gets an error response, not an exception."""
        backend = LazyDockerSandboxBackend(
            session_id="sess-123",
            environment_id="env-123",
            agent_id="agent-123",
            packages={},
            resource_limits={},
            repositories=[],
            repo_secrets={},
            skill_repos=[],
            ip_subnet=None,
            base_image=None,
            sandbox_service_url="http://sandbox:8090",
            api_key=None,
            platform_url="http://localhost:2026",
        )

        mock_client = MagicMock()
        err_resp = httpx.Response(
            status_code=500,
            content=b"Internal Server Error",
            request=httpx.Request("POST", "http://test"),
        )
        http_err = httpx.HTTPStatusError("500", request=err_resp.request, response=err_resp)
        err_resp.raise_for_status = MagicMock(side_effect=http_err)
        mock_client.post.return_value = err_resp
        backend._client = mock_client

        result = backend.execute("echo hello")

        assert result.exit_code == 1
        assert "Failed to create sandbox" in result.output

    def test_upload_files_lazy(self):
        """upload_files triggers container creation just like execute."""
        backend = LazyDockerSandboxBackend(
            session_id="sess-123",
            environment_id="env-123",
            agent_id="agent-123",
            packages={},
            resource_limits={},
            repositories=[],
            repo_secrets={},
            skill_repos=[],
            ip_subnet=None,
            base_image=None,
            sandbox_service_url="http://sandbox:8090",
            api_key=None,
            platform_url="http://localhost:2026",
        )

        lazy_mock = MagicMock()
        create_resp = MagicMock()
        create_resp.status_code = 201
        create_resp.json.return_value = {"container_id": "upload-container", "status": "running"}
        create_resp.raise_for_status = MagicMock()

        platform_resp = MagicMock()
        platform_resp.status_code = 204
        platform_resp.raise_for_status = MagicMock()

        lazy_mock.post.side_effect = [create_resp, platform_resp]
        backend._client = lazy_mock

        backend._ensure_backend()

        inner_mock = MagicMock()
        upload_resp = MagicMock()
        upload_resp.status_code = 200
        upload_resp.json.return_value = [{"path": "test.py", "error": None}]
        upload_resp.raise_for_status = MagicMock()
        inner_mock.post.return_value = upload_resp
        backend._backend._client = inner_mock

        results = backend.upload_files([("test.py", b"print('hi')")])

        assert len(results) == 1
        assert results[0].error is None
