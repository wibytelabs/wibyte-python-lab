from fastapi import APIRouter,HTTPException
from pydantic import BaseModel
from backend.app.services.lab_service import lab_service
from backend.app.auth import CurrentUser
from backend.app.runtime.file_errors import file_error

router=APIRouter()

class FileWriteRequest(BaseModel):
    content: str

class CreateFileRequest(BaseModel):
    path: str
    type: str='file'

class RenameFileRequest(BaseModel):
    old_path: str
    new_path: str


def owned(lab_id,user):
    session=lab_service.get_for_student(lab_id,user.id)
    if session is None:raise HTTPException(404,'Lab not found')
    return session


def operation(call):
    try:return call()
    except HTTPException:raise
    except Exception as error:raise file_error(error) from None


@router.get('/labs/{lab_id}/files')
def list_files(lab_id: str,path: str='.',user: CurrentUser=None):
    session=owned(lab_id,user)
    return {'path':path,'files':operation(lambda:router.workspace_service.list_files(session.container_id,path))}


@router.get('/labs/{lab_id}/files/{path:path}')
def read_file(lab_id: str,path: str,user: CurrentUser=None):
    session=owned(lab_id,user)
    return {'path':path,'content':operation(lambda:router.workspace_service.read_file(session.container_id,path))}


@router.put('/labs/{lab_id}/files/{path:path}')
def write_file(lab_id: str,path: str,request: FileWriteRequest,user: CurrentUser=None):
    session=owned(lab_id,user)
    operation(lambda:router.workspace_service.write_file(session.container_id,path,request.content))
    return {'path':path,'status':'saved'}


@router.post('/labs/{lab_id}/files')
def create_file(lab_id: str,request: CreateFileRequest,user: CurrentUser=None):
    session=owned(lab_id,user)
    if request.type not in ('file','directory'):raise HTTPException(400,"Type must be 'file' or 'directory'")
    method=router.workspace_service.create_directory if request.type=='directory' else router.workspace_service.create_file
    operation(lambda:method(session.container_id,request.path))
    return {'path':request.path,'type':request.type,'status':'created'}


@router.post('/labs/{lab_id}/files/rename')
def rename_file(lab_id: str,request: RenameFileRequest,user: CurrentUser=None):
    session=owned(lab_id,user)
    operation(lambda:router.workspace_service.rename(session.container_id,request.old_path,request.new_path))
    return {'old_path':request.old_path,'new_path':request.new_path,'status':'renamed'}


@router.delete('/labs/{lab_id}/files/{path:path}')
def delete_file(lab_id: str,path: str,user: CurrentUser=None):
    session=owned(lab_id,user)
    operation(lambda:router.workspace_service.delete(session.container_id,path))
    return {'path':path,'status':'deleted'}


router.workspace_service=None
from backend.app.routes.file_transfer import register_file_transfers
register_file_transfers(router)
