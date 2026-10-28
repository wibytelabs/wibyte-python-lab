"""Scoped legacy route error projection; no runtime/path output is echoed."""
from fastapi import HTTPException
from backend.app.runtime.container_files import WorkspaceLimitError,WorkspaceConflictError,WorkspaceCleanupError


def file_error(error):
    if isinstance(error,WorkspaceCleanupError):return HTTPException(500,'File operation completed, but temporary staging cleanup failed. Reload before retrying.')
    if isinstance(error,WorkspaceLimitError):return HTTPException(413,'Maximum file size is 10 MB; directory traversal is also bounded.')
    if isinstance(error,WorkspaceConflictError):return HTTPException(409,'Workspace changed. Reload before retrying.')
    if isinstance(error,FileNotFoundError):return HTTPException(404,'File or folder not found.')
    if isinstance(error,FileExistsError):return HTTPException(409,'A file or directory with that name already exists.')
    if isinstance(error,ValueError):return HTTPException(400,'Invalid or protected workspace path or file content.')
    return HTTPException(500,'Workspace operation failed.')
