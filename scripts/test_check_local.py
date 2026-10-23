"""Runner failure propagation and source-isolation contracts; no Docker operations."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("check_local", Path(__file__).with_name("check_local.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def test_failed_child_is_not_green(self):
        with self.assertRaisesRegex(runner.CheckError, "exit code 7"):
            runner.run_checked("synthetic failure", [sys.executable, "-c", "raise SystemExit(7)"],
                               timeout=5, env={})

    def test_missing_child_is_not_green(self):
        with self.assertRaisesRegex(runner.CheckError, "executable is missing"):
            runner.run_checked("synthetic missing", ["/wpl-p01-no-such-executable"],
                               timeout=5, env={})

    def test_child_timeout_is_bounded(self):
        with self.assertRaisesRegex(runner.CheckError, "timed out"):
            runner.run_checked("synthetic timeout",
                               [sys.executable, "-c", "import time; time.sleep(5)"],
                               timeout=0.05, env={})

    def test_empty_suite_is_not_green(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            result = subprocess.run(
                [sys.executable, "-c", runner.unit_code(root, ["test_empty.py"])],
                env={}, capture_output=True, text=True, timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No tests discovered", result.stderr)

    def test_skipped_suite_is_not_green(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "scripts/test_skip.py").write_text(
                "import unittest\n"
                "class Fixture(unittest.TestCase):\n"
                "    @unittest.skip('synthetic unavailable dependency')\n"
                "    def test_unavailable(self): pass\n"
            )
            result = subprocess.run(
                [sys.executable, "-c", runner.unit_code(root, ["test_skip.py"])],
                env={}, capture_output=True, text=True, timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("skipped=1", result.stderr)

    def test_missing_runtime_image_requires_prepare(self):
        with patch.object(runner, "backend_image", return_value="synthetic-image"), \
                patch.object(runner, "image_exists", return_value=False):
            with self.assertRaisesRegex(runner.CheckError, "--prepare"):
                runner.prepare_images(Path("/unused"), Path("/unused"), {}, False)

    def test_main_returns_failure(self):
        with patch.object(runner, "execute", side_effect=runner.CheckError("synthetic")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(runner.main([]), 1)

    def test_missing_tool_fails_prerequisites(self):
        with patch.object(runner.shutil, "which", return_value=None):
            with self.assertRaisesRegex(runner.CheckError, "Docker CLI is missing"):
                runner.prerequisites(Path("/unused"), {"PATH": os.defpath})

    def fixture(self, root):
        for filename in runner.FILES:
            path = root / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic fixture")
        for directory in runner.TREES:
            (root / directory).mkdir(parents=True, exist_ok=True)

    def test_snapshot_excludes_private_and_runtime_files(self):
        with tempfile.TemporaryDirectory() as directory:
            source, snapshot = Path(directory) / "source", Path(directory) / "snapshot"
            source.mkdir()
            snapshot.mkdir()
            self.fixture(source)
            for filename in ("backend/.env", "frontend/.env.local", "frontend/src/.env",
                             "backend/app/fixture.db", "backend/app/token.pem"):
                (source / filename).write_text("synthetic excluded marker")
            (source / "backend/app/fixture.py").write_text("pass")
            runner.copy_sources(source, snapshot)
            self.assertTrue((snapshot / "backend/app/fixture.py").is_file())
            for filename in ("backend/.env", "frontend/.env.local", "frontend/src/.env",
                             "backend/app/fixture.db", "backend/app/token.pem"):
                self.assertFalse((snapshot / filename).exists())
            self.assertEqual(snapshot.stat().st_mode & 0o777, 0o755)

    def test_snapshot_refuses_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            source, snapshot = Path(directory) / "source", Path(directory) / "snapshot"
            source.mkdir()
            snapshot.mkdir()
            self.fixture(source)
            outside = Path(directory) / "outside"
            outside.write_text("synthetic private marker")
            (source / "frontend/src/escape.ts").symlink_to(outside)
            with self.assertRaisesRegex(runner.CheckError, "symlink"):
                runner.copy_sources(source, snapshot)

    def test_backend_command_has_no_network_or_docker_socket(self):
        with patch.object(runner, "run_checked") as run:
            run.return_value = subprocess.CompletedProcess([], 1, stdout="")
            runner.run_container("fixture", "synthetic-image", Path("/synthetic"),
                                 ["python", "-V"], {"WPL_PUBLIC_URL": "http://localhost:8080"}, {})
            arguments = run.call_args_list[0].args[1]
            self.assertIn("--read-only", arguments)
            self.assertIn("--network", arguments)
            self.assertEqual(arguments[arguments.index("--network") + 1], "none")
            self.assertFalse(any("/var/run/docker.sock" in value for value in arguments))
            self.assertIn("readonly", next(value for value in arguments if value.startswith("type=bind")))
            self.assertIn("-i", arguments)


if __name__ == "__main__":
    unittest.main()
