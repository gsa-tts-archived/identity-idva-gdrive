"""
gdrive rest api
"""

import base64 as base64decoder
import io
import logging
import zipfile
import json

import fastapi
from fastapi import Response, status, responses

from googleapiclient.http import HttpError
from starlette.requests import Request

from pydantic import BaseModel

from . import drive_client, settings

log = logging.getLogger(__name__)

router = fastapi.APIRouter()

drive_client.init()


# Patch zip decodeExtra to ignore invalid extra data
def nullDecode(self):
    return


zipfile.ZipInfo._decodeExtra = nullDecode  # type: ignore


@router.post("/upload")
async def upload_file(
    id,
    filename,
    request: Request,
    response: Response,
    base64: bool = False,
    zip: bool = False,
):
    """
    Upload file to gdrive.
    """

    try:
        body = await request.body()

        if base64:
            body = base64decoder.b64decode(body)

        stream = io.BytesIO(body)

        parent = drive_client.create_folder(id, settings.ROOT_DIRECTORY)

        if zip:
            with zipfile.ZipFile(stream) as archive:
                files = archive.filelist
                for file in files:
                    image = io.BytesIO(archive.read(file))
                    drive_client.upload_basic(
                        f"{filename}_{file.filename}", parent, image
                    )
        else:
            drive_client.upload_basic(filename, parent, stream)

    except HttpError as error:
        log.error(f"An error occurred: {error}")
        response.status_code = error.status_code


@router.delete("/upload")
async def delete_file(filename, response: Response):
    """
    Delete file from gdrive.
    """

    try:
        files = drive_client.get_files(filename)
        if files:
            for file in files:
                drive_client.delete_file(file["id"])
        else:
            response.status_code = status.HTTP_404_NOT_FOUND

    except HttpError as error:
        log.error(f"An error occurred: {error}")
        response.status_code = error.status_code


class FileModel(BaseModel):
    folder_name: str
    drive_id: str
    parent_id: str | None = None


@router.post("/create/folder")
async def create_folder(request: FileModel):
    """
    Create a folder in gdrive
    """

    if not request.parent_id:
        request.parent_id = request.drive_id

    try:
        new_folder = drive_client.create_folder(request.folder_name, request.parent_id)

        return responses.JSONResponse(
            status_code=202,
            content={"id": new_folder},
        )

    except HttpError as error:
        log.error(f"An error occurred: {error}")
        responses.JSONResponse(status_code=404, content="exception")


class CopyModel(BaseModel):
    source_id: str
    destination_id: str
    new_name: str | None = None


@router.post("/copy")
async def copy_file(request: CopyModel):
    """
    Copy a file in gdrive
    """

    try:
        new_file = drive_client.copy_file(
            request.source_id, request.destination_id, request.new_name
        )

        return responses.JSONResponse(
            status_code=202,
            content={"id": new_file},
        )

    except HttpError as error:
        log.error(f"An error occurred: {error}")
        responses.JSONResponse(status_code=404, content="exception")


class FileModel(BaseModel):
    resourceId: str
    fields: str | None = None


@router.post("/get")
async def get_file(request: FileModel):
    try:
        file_info = drive_client.get_file(request.resourceId, request.fields)
        # breakpoint()
        return responses.JSONResponse(
            status_code=202,
            content=file_info,
        )

    except HttpError as error:
        log.error(f"An error occurred: {error}")
        responses.JSONResponse(status_code=404, content="exception")


class ResourceModel(BaseModel):
    resourceId: str


@router.post("/download/json")
async def download_file(request: ResourceModel):
    """
    Copy a file in gdrive
    """

    try:
        new_file = drive_client.download_file(request.resourceId)

        return responses.JSONResponse(
            status_code=202,
            content=json.loads(new_file.decode("utf-8")),
        )

    except HttpError as error:
        log.error(f"An error occurred: {error}")
        responses.JSONResponse(status_code=404, content="exception")
