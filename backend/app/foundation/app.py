"""Independent factory; business routes follow in later P02 checkpoints."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.app.foundation.settings import FoundationSettings
from backend.app.foundation.db import FoundationDatabase

def create_app(settings: FoundationSettings) -> FastAPI:
    database = FoundationDatabase(settings) if settings.enabled else None
    @asynccontextmanager
    async def lifespan(app):
        try:
            if database:
                database.verify_runtime_role()
            yield
        finally:
            if database:
                database.close()
    app = FastAPI(title="WPL tenant foundation", lifespan=lifespan)
    app.state.foundation_database = database
    return app
