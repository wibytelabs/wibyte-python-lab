#!/usr/bin/env python3
"""Owner-only migration command; no dotenv, implicit target or import-time DDL."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.foundation.migrate import migrate, FoundationMigrationError
from backend.app.foundation.settings import FoundationConfigurationError

def main():
    try:
        migrate(os.environ.get("WPL_MIGRATION_DATABASE_URL", ""))
    except (FoundationConfigurationError, FoundationMigrationError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Foundation migration completed.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
