"""Configuration tests using disposable source and dotenv fixtures only."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class IdleDefaultsTests(unittest.TestCase):
    def evaluate(self, process_value=None, file_value=None):
        with tempfile.TemporaryDirectory(prefix="wpl-idle-fixture-") as directory:
            root = Path(directory)
            config = root / "backend/app/config.py"
            config.parent.mkdir(parents=True)
            source = Path(__file__).resolve().parents[1] / "backend/app/config.py"
            shutil.copyfile(source, config)
            if file_value is not None:
                (root / "backend/.env").write_text(
                    f"WPL_IDLE_MINUTES={file_value}\n"
                )
            environment = {
                "PATH": os.defpath,
                "HOME": directory,
                "PYTHONDONTWRITEBYTECODE": "1",
                "WPL_PUBLIC_URL": "http://localhost:8080",
                "WPL_DATABASE_PATH": str(root / "fixture.db"),
            }
            if process_value is not None:
                environment["WPL_IDLE_MINUTES"] = process_value
            return subprocess.run(
                [sys.executable, "-c",
                 "import runpy; "
                 f"print(runpy.run_path({str(config)!r})['IDLE_MINUTES'])"],
                cwd=root, env=environment, capture_output=True,
                text=True, timeout=15,
            )

    def assert_idle(self, expected, **values):
        result = self.evaluate(**values)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(expected))

    def test_omitted_default_is_35(self):
        self.assert_idle(35)

    def test_explicit_positive_process_overrides_are_preserved(self):
        for value in ("30", "45"):
            with self.subTest(value=value):
                self.assert_idle(int(value), process_value=value)

    def test_dotenv_override_and_process_precedence(self):
        self.assert_idle(30, file_value="30")
        self.assert_idle(45, process_value="45", file_value="30")
        self.assert_idle(30, process_value="30", file_value="45")

    def test_invalid_idle_values_fail_clearly(self):
        for value in ("0", "-1", "invalid", "1.5", ""):
            with self.subTest(value=value):
                result = self.evaluate(process_value=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "WPL_IDLE_MINUTES must be a positive integer.",
                    result.stderr,
                )


if __name__ == "__main__":
    unittest.main()
