import errno
import io
import unittest
import tempfile
from pathlib import Path
from contextlib import redirect_stdout
from unittest import mock

import scripts.ux_dashboard
from dashboard import server


class DashboardPortSelectionTests(unittest.TestCase):
    def test_launcher_receipt_uses_actual_port(self):
        http = mock.Mock(server_address=("127.0.0.1", 8001))
        http.serve_forever.side_effect = KeyboardInterrupt
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "ready.url"
            with mock.patch.object(server, "_ensure_config_env"), mock.patch.object(server, "_bind_server", return_value=http):
                server.run_server(["--port", "8000", "--ready-file", str(receipt)])
            self.assertEqual(receipt.read_text().strip(), "http://127.0.0.1:8001/")
            http.server_close.assert_called_once()

    def test_stale_receipt_is_rejected_without_overwrite(self):
        http = mock.Mock(server_address=("127.0.0.1", 8001))
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "ready.url"
            receipt.write_text("old receipt")
            with mock.patch.object(server, "_ensure_config_env"), mock.patch.object(server, "_bind_server", return_value=http):
                with self.assertRaises(FileExistsError):
                    server.run_server(["--ready-file", str(receipt)])
            self.assertEqual(receipt.read_text(), "old receipt")
            http.server_close.assert_called_once()
            http.serve_forever.assert_not_called()

    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_requested_port_is_preserved_when_available(self):
        with mock.patch.object(server, "_windows_listener_ports", return_value=set()), mock.patch.object(server, "ThreadingHTTPServer") as factory:
            self.assertIs(server._bind_server("127.0.0.1", 8000), factory.return_value)
            factory.assert_called_once_with(("127.0.0.1", 8000), server.DashboardHandler)

    def test_windows_conflict_is_skipped_before_binding(self):
        with mock.patch.object(server, "_windows_listener_ports", return_value={8000}), mock.patch.object(server, "ThreadingHTTPServer") as factory:
            server._bind_server("127.0.0.1", 8000)
            factory.assert_called_once_with(("127.0.0.1", 8001), server.DashboardHandler)

    def test_busy_and_permission_denied_ports_are_skipped(self):
        with mock.patch.object(server, "_windows_listener_ports", return_value=set()), mock.patch.object(server, "ThreadingHTTPServer", side_effect=[OSError(errno.EADDRINUSE, "busy"), PermissionError(errno.EACCES, "denied"), mock.sentinel.http]) as factory:
            self.assertIs(server._bind_server("127.0.0.1", 8000), mock.sentinel.http)
            self.assertEqual([call.args[0][1] for call in factory.call_args_list], [8000, 8001, 8002])

    def test_strict_port_does_not_fallback(self):
        with mock.patch.object(server, "_windows_listener_ports", return_value={8000}), mock.patch.object(server, "ThreadingHTTPServer") as factory:
            with self.assertRaises(SystemExit):
                server._bind_server("127.0.0.1", 8000, strict_port=True)
            factory.assert_not_called()

    def test_attempts_are_bounded_and_do_not_exceed_tcp_range(self):
        for port, expected in [(8000, 20), (65535, 1)]:
            with self.subTest(port=port), mock.patch.object(server, "_windows_listener_ports", return_value=set()), mock.patch.object(server, "ThreadingHTTPServer", side_effect=OSError(errno.EADDRINUSE, "busy")) as factory:
                with self.assertRaises(SystemExit):
                    server._bind_server("127.0.0.1", port)
                self.assertEqual(factory.call_count, expected)

    def test_unrelated_os_error_is_not_hidden(self):
        with mock.patch.object(server, "_windows_listener_ports", return_value=set()), mock.patch.object(server, "ThreadingHTTPServer", side_effect=OSError(errno.EMFILE, "too many files")) as factory:
            with self.assertRaises(OSError):
                server._bind_server("127.0.0.1", 8000)
            self.assertEqual(factory.call_count, 1)

    def test_windows_listener_probe_parses_ports(self):
        with mock.patch.dict(server.os.environ, {"WSL_DISTRO_NAME": "test"}), mock.patch.object(server.shutil, "which", return_value="powershell.exe"), mock.patch.object(server.subprocess, "run", return_value=mock.Mock(stdout="8000\n8765\n8000\n")):
            self.assertEqual(server._windows_listener_ports(), {8000, 8765})

    def test_windows_probe_failure_warns_and_allows_local_check(self):
        with mock.patch.dict(server.os.environ, {"WSL_DISTRO_NAME": "test"}), mock.patch.object(server.shutil, "which", return_value="powershell.exe"), mock.patch.object(server.subprocess, "run", side_effect=OSError("unavailable")), mock.patch("builtins.print") as output:
            self.assertEqual(server._windows_listener_ports(), set())
            self.assertIn("somente o WSL", output.call_args.args[0])

    def test_native_launch_does_not_run_windows_probe(self):
        with mock.patch.dict(server.os.environ, {}, clear=True), mock.patch.object(server.subprocess, "run") as run:
            self.assertEqual(server._windows_listener_ports(), set())
            run.assert_not_called()

    def test_launcher_prints_actual_port_and_closes_server(self):
        http = mock.Mock(server_address=("127.0.0.1", 8001))
        http.serve_forever.side_effect = KeyboardInterrupt
        with mock.patch.object(server, "_ensure_config_env"), mock.patch.object(server, "_bind_server", return_value=http), mock.patch("builtins.print") as output:
            server.run_server(["--host", "127.0.0.1", "--port", "8000"])
            self.assertTrue(any("http://127.0.0.1:8001" in str(call) for call in output.call_args_list))
            http.server_close.assert_called_once()
