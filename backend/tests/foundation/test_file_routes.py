"""Each contract runs actual legacy routes with isolated synthetic identity/Docker transport."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

CASES=(
    'normal_general_routes_keep_response_shapes_and_execute_the_real_adapter',
    'missing_identity_or_foreign_lab_never_resolves_a_container',
    'root_traversal_absolute_git_and_invalid_paths_fail_for_actual_general_routes',
    'symlink_parents_and_targets_cannot_read_write_delete_rename_or_transfer_outside',
    'ten_mib_limit_is_413_on_read_editor_rename_delete_list_upload_and_download',
    'nonregular_and_hardlinked_files_are_denied_by_general_and_transfer_callers',
    'create_and_rename_conflicts_preserve_existing_bytes_with_409',
    'upload_download_keep_raw_bytes_content_headers_and_activity_only_after_success',
    'staging_or_helper_failure_cleans_owned_resources_and_returns_no_raw_diagnostics',
    'staging_cleanup_refuses_unexpected_entry_and_wrong_directory_identity',
    'completed_write_reports_cleanup_failure_truthfully_and_partial_stage_initialization_is_removed',
    'http_missing_file_type_errors_and_shell_characters_preserve_bounded_contract',
    'actual_routes_have_no_legacy_config_import_or_provider_dependency_in_transport_fixture',
)


class FileRouteTests(unittest.TestCase):
    def run_case(self,name):
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('file_route_fixture.py')),'test_'+name],
            cwd='/tmp',env={'PATH':os.environ['PATH'],'PYTHONPATH':'/app','PYTHONDONTWRITEBYTECODE':'1'},
            capture_output=True,text=True,timeout=25)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        if name.startswith('actual_routes_'):print(result.stdout.strip(),flush=True)


def contract(name):
    def check(self):self.run_case(name)
    return check


for name in CASES:setattr(FileRouteTests,'test_'+name,contract(name))
