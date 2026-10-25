"""Failure and ownership contracts; Docker responses in this module are mocked."""
import contextlib
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import check_foundation as runner

class FixtureRunnerTests(unittest.TestCase):
    def test_timeout_is_sanitized_and_nonzero(self):
        with patch.object(runner.subprocess, "run", side_effect=subprocess.TimeoutExpired(["secret"], 1)):
            with self.assertRaises(runner.shared.CheckError) as result:
                runner.checked("fixture timeout", ["secret"], {}, timeout=1)
            self.assertNotIn("secret", str(result.exception))
        with patch.object(runner, "execute", side_effect=runner.shared.CheckError("fixture timeout")), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(runner.main([]), 1)

    def test_cleanup_refuses_foreign_owner(self):
        fixture = runner.Fixture({})
        fixture.register("network", "synthetic")
        with patch.object(runner, "checked", return_value=subprocess.CompletedProcess([], 0, stdout="foreign-id|foreign-owner")) as run:
            with self.assertRaisesRegex(runner.shared.CheckError, "ownership mismatch"):
                fixture.cleanup()
            self.assertEqual(run.call_count, 1)

    def test_cleanup_uses_inspected_id(self):
        fixture = runner.Fixture({})
        fixture.register("container", "synthetic")
        with patch.object(runner, "checked", side_effect=[subprocess.CompletedProcess([], 0, stdout="owned-id|" + fixture.owner),
                subprocess.CompletedProcess([], 0, stdout="")]) as run:
            fixture.cleanup()
            self.assertEqual(run.call_args_list[-1].args[1], ["docker", "rm", "-f", "owned-id"])

    def test_inspection_failure_is_not_treated_as_absence(self):
        fixture = runner.Fixture({})
        fixture.register("network", "synthetic")
        with patch.object(runner, "checked", return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="daemon unavailable")):
            with self.assertRaisesRegex(runner.shared.CheckError, "inspection failed"):
                fixture.cleanup()

    def test_failed_and_timed_out_stage_always_cleans(self):
        for reason in ("synthetic failure", "synthetic timeout"):
            with self.subTest(reason=reason), patch.object(runner.shared, "prerequisites"), \
                    patch.object(runner.shared, "prepare_images", return_value="synthetic"), \
                    patch.object(runner.shared, "image_exists", return_value=True), \
                    patch.object(runner.shared, "copy_sources"), patch.object(runner.Fixture, "start"), \
                    patch.object(runner.Fixture, "test", side_effect=runner.shared.CheckError(reason)), \
                    patch.object(runner.Fixture, "cleanup") as cleanup:
                with self.assertRaises(runner.shared.CheckError):
                    runner.execute(False)
                cleanup.assert_called_once()

    def test_test_container_only_has_fixture_network_and_readonly_snapshot(self):
        fixture = runner.Fixture({})
        with patch.object(runner, "checked") as run:
            fixture.test("synthetic-image", Path("/synthetic-source"), "pass", "fixture")
            args = run.call_args.args[1]
            self.assertEqual(args[args.index("--network") + 1], fixture.network)
            self.assertIn("type=bind,src=/synthetic-source,dst=/app,readonly", args)
            self.assertIn("-i", args)
            self.assertFalse(any("docker.sock" in value or "--privileged" in value for value in args))
