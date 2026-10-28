
import asyncio
from urllib.parse import quote

from fastapi import HTTPException, Request, Response

from backend.app.auth import CurrentUser
from backend.app.services.lab_service import lab_service

from backend.app.runtime import container_files as files
from backend.app.runtime.file_errors import file_error

LIMIT=files.LIMIT


def upload_bytes(container,path,data):
    try:files.staged_write(container,path,data,exclusive=True)
    except Exception as error:raise file_error(error) from None


def download_bytes(container,path):
    try:return files.invoke(container,'download',path)
    except Exception as error:raise file_error(error) from None


def register_file_transfers(router):
    def get_container(lab_id, user):
        session = lab_service.get_for_student(lab_id, user.id)
        if session is None:
            raise HTTPException(status_code=404, detail="Lab not found")
        return router.workspace_service._get_container(session.container_id)

    @router.post("/labs/{lab_id}/upload")
    async def upload_file(
        lab_id: str,
        request: Request,
        path: str,
        user: CurrentUser = None,
    ):
        container = await asyncio.to_thread(get_container, lab_id, user)
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > LIMIT:
                raise HTTPException(status_code=413, detail="Maximum file size is 10 MB.")
            data.extend(chunk)

        await asyncio.to_thread(upload_bytes, container, path, bytes(data))
        await asyncio.to_thread(lab_service.update_activity, lab_id)
        return {"status": "uploaded", "path": path}

    @router.get("/labs/{lab_id}/download")
    def download_file(
        lab_id: str,
        path: str,
        user: CurrentUser = None,
    ):
        container = get_container(lab_id, user)
        data = download_bytes(container, path)
        lab_service.update_activity(lab_id)
        filename = quote(path.rsplit("/", 1)[-1], safe="")
        return Response(
            content=data,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": "attachment; filename*=UTF-8''" + filename,
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
