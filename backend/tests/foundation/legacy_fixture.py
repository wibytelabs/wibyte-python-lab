"""Synthetic legacy snapshots built by the unchanged historical revision bodies."""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
import os
import sqlite3
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

STUDENT='11111111-1111-4111-8111-111111111111'
OTHER='22222222-2222-4222-8222-222222222222'
CONNECTION='33333333-3333-4333-8333-333333333333'
REPOSITORY='44444444-4444-4444-8444-444444444444'
LAB='55555555-5555-4555-8555-555555555555'
ACCESS='synthetic-access-token-do-not-print'
REFRESH='synthetic-refresh-token-do-not-print'
NOW='2026-10-27 00:00:00'
REVISIONS=('3b52e55b620b','553a7ddf4183','3e58a6eb699a','7d8e63fb45c3')


def upgrade(path,revision):
    versions=Path(__file__).resolve().parents[2]/'alembic/versions'
    filename=next(versions.glob(revision+'_*.py'))
    spec=spec_from_file_location('fixture_revision_'+revision,filename)
    module=module_from_spec(spec);spec.loader.exec_module(module)
    engine=create_engine('sqlite:///'+str(path))
    try:
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
            connection.exec_driver_sql('CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)')
            connection.exec_driver_sql('DELETE FROM alembic_version')
            connection.exec_driver_sql('INSERT INTO alembic_version VALUES (?)',(revision,))
    finally:engine.dispose()
    os.chmod(path,0o600)


def fixture(path,*,populated=True):
    for revision in REVISIONS:upgrade(path,revision)
    if populated:
        with sqlite3.connect(path) as connection:
            connection.execute('PRAGMA foreign_keys=ON')
            for identifier in (STUDENT,OTHER):
                connection.execute('INSERT INTO students(id,name,email,created_at,updated_at) VALUES (?,?,?,?,?)',
                    (identifier,'Synthetic fixture','duplicate@example.invalid',NOW,NOW))
            connection.execute('INSERT INTO github_connections VALUES (?,?,?,?,?,?,?,?,?,?)',
                (CONNECTION,STUDENT,'12345','synthetic-owner',ACCESS,NOW,NOW,REFRESH,'2026-10-28 00:00:00','2027-01-01 00:00:00'))
            connection.execute('INSERT INTO github_repositories VALUES (?,?,?,?,?,?,?,?,?)',
                (REPOSITORY,STUDENT,'67890','synthetic-owner','synthetic-repo','synthetic-owner/synthetic-repo','main',NOW,NOW))
            connection.execute('INSERT INTO labs VALUES (?,?,?,?,?,?,?)',(LAB,STUDENT,'synthetic-container-id','running',NOW,NOW,REPOSITORY))
    return path


def historical_fixture(path):
    for revision in REVISIONS[:2]:upgrade(path,revision)
    with sqlite3.connect(path) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        for identifier in (STUDENT,OTHER):connection.execute('INSERT INTO students VALUES (?,?)',(identifier,NOW))
        connection.execute('INSERT INTO github_connections VALUES (?,?,?,?,?,?,?)',
            (CONNECTION,STUDENT,'12345','synthetic-owner',ACCESS,NOW,NOW))
        connection.execute('INSERT INTO github_repositories VALUES (?,?,?,?,?,?,?,?,?)',
            (REPOSITORY,STUDENT,'67890','synthetic-owner','synthetic-repo','synthetic-owner/synthetic-repo','main',NOW,NOW))
        connection.execute('INSERT INTO labs VALUES (?,?,?,?,?,?,?)',
            (LAB,STUDENT,'synthetic-container-id','running',NOW,NOW,REPOSITORY))
    return path
