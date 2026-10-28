"""Existing workspace API implemented through the trusted safe file adapter."""
import json
import docker
from backend.app.runtime import container_files as files


class WorkspaceService:
    WORKSPACE_ROOT=files.ROOT

    def __init__(self,docker_client: docker.DockerClient):self.docker_client=docker_client

    def _get_container(self,container_id: str):return self.docker_client.containers.get(container_id)

    def list_files(self,container_id: str,path: str='.'):
        raw=files.invoke(self._get_container(container_id),'list',path)
        try:
            value=json.loads(raw)
            if not isinstance(value,list) or len(value)>4096:raise ValueError
            for item in value:
                if not isinstance(item,dict) or set(item)!={'name','type'} or item['type'] not in ('file','directory'):raise ValueError
                files.file_ops.parts(item['name'])
                if '/' in item['name']:raise ValueError
            return value
        except (ValueError,TypeError,AttributeError):raise files.WorkspaceOperationError('Invalid workspace response.') from None

    def read_file(self,container_id: str,path: str):
        return files.invoke(self._get_container(container_id),'read',path).decode('utf-8',errors='replace')

    def write_file(self,container_id: str,path: str,content: str):
        try:data=content.encode('utf-8')
        except (AttributeError,UnicodeError):raise ValueError('Invalid file content.') from None
        files.staged_write(self._get_container(container_id),path,data,exclusive=False)

    def create_file(self,container_id: str,path: str):files.invoke(self._get_container(container_id),'create',path)
    def create_directory(self,container_id: str,path: str):files.invoke(self._get_container(container_id),'mkdir',path)
    def delete(self,container_id: str,path: str):files.invoke(self._get_container(container_id),'delete',path)
    def rename(self,container_id: str,old_path: str,new_path: str):files.invoke(self._get_container(container_id),'rename',old_path,new_path)
