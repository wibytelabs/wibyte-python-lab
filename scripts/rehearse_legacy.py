#!/usr/bin/env python3
"""Explicit snapshot dry run or confirmed owned-fixture archival import; never live migration."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.domains.migration.snapshot import ARCHIVE_POLICY,SnapshotError,inspect_snapshot


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',required=True,type=Path,help='Private regular *.snapshot.sqlite3 copy; never the live DB.')
    parser.add_argument('--sha256',required=True,help='Expected checksum of the supplied consistent snapshot.')
    parser.add_argument('--historical-policy',choices=[ARCHIVE_POLICY],help='Explicitly archive supported older schema; credentials require reauthorization.')
    parser.add_argument('--confirm-disposable-import',action='store_true')
    parser.add_argument('--confirm-source-sha256')
    parser.add_argument('--disposable-target-url')
    parser.add_argument('--fixture-owner')
    parser.add_argument('--source-namespace')
    parser.add_argument('--reason')
    parser.add_argument('--key-file',type=Path)
    parser.add_argument('--key-reference')
    parser.add_argument('--identity-bindings',type=Path,help='Optional private JSON of explicit source UUID to existing auth UUID; never emails.')
    arguments=parser.parse_args(argv)
    inputs=(arguments.confirm_source_sha256,arguments.disposable_target_url,arguments.fixture_owner,arguments.source_namespace,
        arguments.reason,arguments.key_file,arguments.key_reference)
    if not arguments.confirm_disposable_import and (any(value is not None for value in inputs) or arguments.identity_bindings):
        parser.error('Import inputs require --confirm-disposable-import; default mode only reads the snapshot.')
    if arguments.confirm_disposable_import and not all(inputs):parser.error('Confirmed import requires all explicit target, confirmation, namespace, reason and key inputs.')
    try:snapshot=inspect_snapshot(arguments.snapshot,arguments.sha256,historical_policy=arguments.historical_policy)
    except SnapshotError as error:
        print(str(error),file=sys.stderr);return 2
    if not arguments.confirm_disposable_import:
        print(json.dumps(snapshot.report(),sort_keys=True));return 0
    # Import-only dependencies/settings have no dry-run side effects or env fallback.
    import psycopg
    from backend.app.foundation.settings import postgres_url,FoundationConfigurationError
    from backend.app.domains.jobs.payloads import PayloadCipher,PayloadKeyUnavailable,InvalidPayload
    from backend.app.domains.migration.importer import RehearsalError,prepare_import,import_prepared
    from backend.app.domains.migration.cli_inputs import FileKeys,read_bindings
    try:
        if arguments.confirm_source_sha256!=snapshot.checksum:raise RehearsalError('explicit_import_confirmation_required')
        url=postgres_url(arguments.disposable_target_url,'disposable target')
        if url.host!='fixture-db' or url.database!='wpl_fixture' or url.username!='wpl_migrator' or url.port not in (None,5432):
            raise RehearsalError('owned_disposable_target_required')
        cipher=PayloadCipher(FileKeys(arguments.key_file,arguments.key_reference))
        bindings=read_bindings(arguments.identity_bindings) if arguments.identity_bindings else None
        prepared=prepare_import(snapshot,arguments.source_namespace,arguments.reason,cipher,identity_bindings=bindings)
        with psycopg.connect(url.set(drivername='postgresql').render_as_string(hide_password=False),connect_timeout=5,
                application_name='wpl-legacy-rehearsal',options='-c statement_timeout=5000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=10000') as connection:
            result=import_prepared(connection,prepared,fixture_owner=arguments.fixture_owner,confirm_source_sha256=arguments.confirm_source_sha256)
        # Emit success only after the outer connection context committed.
        print(json.dumps(result,sort_keys=True));return 0
    except (RehearsalError,PayloadKeyUnavailable,InvalidPayload) as error:
        print(str(error),file=sys.stderr);return 2
    except (FoundationConfigurationError,psycopg.Error):
        print('Disposable import failed; target details redacted.',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
