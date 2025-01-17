import io
import logging
import json
import mimetypes
from typing import List

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError


from gdrive import settings, error

log = logging.getLogger(__name__)

creds = service_account.Credentials.from_service_account_info(
    settings.CREDENTIALS, scopes=settings.SCOPES
)

service = build("drive", "v3", credentials=creds)


def init():
    drive = drives_list()
    result = (
        service.files()
        .get(fileId=settings.ROOT_DIRECTORY, supportsAllDrives=True)
        .execute()
    )
    driveId = result["id"]
    log.info(f"Connected to Root Directory {driveId}")


def list(count: int = 10, shared: bool = True) -> None:
    """
    Prints the names and ids of the first <count> files the user has access to.
    """

    results = (
        service.files()
        .list(
            pageSize=count,
            fields="*",
            supportsAllDrives=shared,
            includeItemsFromAllDrives=shared,
        )
        .execute()
    )
    items = results.get("files", [])

    if not items:
        log.info("No files found.")
        return
    log.info("Files:")
    log.info("name (id) parents trashed")
    for item in items:
        try:
            log.info(
                "{0} ({1}) {2} {3}".format(
                    item["name"], item["id"], item["parents"], item["trashed"]
                )
            )
        except KeyError as error:
            log.info(f"No such key: {error} in {item}")


def create_empty_spreadsheet(filename: str, parent_id: str) -> str:
    file_metadata = {
        "name": filename,
        "parents": [parent_id],
        "mimeType": "application/vnd.google-apps.spreadsheet",
    }

    file = (
        service.files()
        .create(body=file_metadata, fields="id", supportsAllDrives=True)
        .execute()
    )

    return file.get("id")


def drives_list():
    """
    List available shared drives
    """

    result = service.drives().list().execute()
    return result


def upload_basic(filename: str, parent_id: str, bytes: io.BytesIO) -> str:
    """
    Upload new file to given  parent folder
    Returns : Id of the file uploaded
    """

    file_metadata = {"name": filename, "parents": [parent_id]}

    mimetype, _ = mimetypes.guess_type(filename)
    if mimetype is None:
        # Guess failed, use octet-stream.
        mimetype = "application/octet-stream"

    media = MediaIoBaseUpload(bytes, mimetype=mimetype)

    file = (
        service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )

    log.debug(f'File ID: {file.get("id")}')

    return file.get("id")


def create_folder(name: str, parent_id: str) -> str:
    """
    Create a folder and prints the folder ID
    Returns : Folder Id
    """

    file_metadata = {
        "name": name,
        "parents": [parent_id],
        "mimeType": "application/vnd.google-apps.folder",
    }

    existing = (
        service.files()
        .list(
            q=f"name='{name}' and '{parent_id}' in parents and trashed=false",
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
        .get("files", [])
    )

    if not existing:
        file = (
            service.files()
            .create(body=file_metadata, fields="id", supportsAllDrives=True)
            .execute()
        )
        log.debug(f'Folder has created with ID: "{file.get("id")}".')
    else:
        file = existing[0]
        log.debug("Folder already exists")

    return file.get("id")


def get_files(filename: str) -> List:
    """
    Get list of files by filename
    """
    results = (
        service.files()
        .list(
            q=f"name = '{filename}'",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    return results["files"]


def get_files_by_drive_id(filename: str, drive_id: str):
    """
    Get list of files by filename
    """

    results = (
        service.files()
        .list(
            q=f"name = '{filename}'",
            corpora="drive",
            driveId=drive_id,
            includeTeamDriveItems=True,
            supportsTeamDrives=True,
        )
        .execute()
    )

    return results["files"]


def get_files_in_folder(id: str) -> List:
    """
    Get list of files within a folder by folder ID
    """
    files = []
    page_token = None
    while True:
        results = (
            service.files()
            .list(
                q=f"'{id}' in parents and trashed=false",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                fields="nextPageToken, files(*)",
                pageToken=page_token,
            )
            .execute()
        )
        files.extend(results.get("files", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break
    return files


def delete_file(id: str) -> None:
    """
    Delete file by id
    """

    service.files().delete(fileId=id, supportsAllDrives=True).execute()


def export(id: str) -> any:
    return service.files().get_media(fileId=id).execute()


def get_labels(Id: str, count: int = 10) -> List:
    page_token = None
    labels = []
    while True:
        results = (
            service.files()
            .listLabels(fileId=Id, maxResults=count, pageToken=page_token)
            .execute()
        )

        labels.extend(results.get("labels", []))
        page_token = results.get("nextPageToken")

        if not page_token:
            break

    return labels


def edit_description(Id: str, text: List) -> List:
    file_metadata = f"{text[0]}"
    results = (
        service.files()
        .update(fileId=Id, supportsAllDrives=True, body=file_metadata)
        .execute()
    )

    return (
        service.files()
        .get(fileId=Id, supportsAllDrives=True, fields="description, properties")
        .execute()
    )


def get_files_by_query(query: str, driveId: str | None, fields: List | None = []):
    """
    Get list of files by query
    """
    files = []
    page_token = None

    service_input_args = {
        "q": query,
        "includeTeamDriveItems": True,
        "supportsTeamDrives": True,
    }

    # if fields:
    #     separator = ", "
    #     fields_input = separator.join(map(str, fields))
    # service_input_args.update({"fields": fields})

    if driveId:
        service_input_args.update({"corpora": "drive", "driveId": driveId})

    while True:
        results = service.files().list(**service_input_args).execute()

        files.extend(results.get("files", []))
        page_token = results.get("nextPageToken")

        if not page_token:
            break
        else:
            service_input_args.update({"pageToken": page_token})

    return files

    # breakpoint()
    # if driveId:
    #     results = ()
    # else:
    #     results = (
    #         service.files()
    #         .list(
    #             q=query,
    #             includeTeamDriveItems=True,
    #             supportsTeamDrives=True,
    #         )
    #         .execute()
    #     )

    # return results["files"]


def edit_metadata(Id: str, metadata: dict, fields: str):
    return (
        service.files()
        .update(
            fileId=Id,
            supportsAllDrives=True,
            body=metadata,
            fields=fields,
        )
        .execute()
    )


def copy_file(
    source_id: str,
    destination_id: str,
    new_name: str | None = None,
    source_parent: str | None = None,
):
    """
    Get list of files by filename
    """
    # Get source file information: name and parent
    source_file = (
        service.files()
        .get(fileId=source_id, fields="parents, name", supportsAllDrives=True)
        .execute()
    )
    new_name = source_file["name"]
    current_location = source_file["parents"][0]

    # Check if file already exists in destination
    existing = (
        service.files()
        .list(
            q=f"name contains '{new_name}' and '{destination_id}' in parents and trashed=false",
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
        .get("files", [])
    )

    if existing:
        new_name = "".join((new_name, f"[{len(existing)}]"))

    return (
        service.files()
        .copy(
            fileId=source_id,
            supportsAllDrives=True,
            body={
                "parents": [destination_id],
                "name": new_name,
            },
        )
        .execute()
    )


def download_file(file_id: str):
    try:
        request = service.files().get_media(fileId=file_id)
        file = io.BytesIO()
        downloader = MediaIoBaseDownload(file, request)
        done = False

        while done is False:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}.")

    except HttpError as error:
        print(f"An error occurred: {error}")
        file = None

    return file.getvalue()


def get_file(file_id: str, fields: str | None = None):
    request = (
        service.files()
        .get(fileId=file_id, fields=fields, supportsAllDrives=True)
        .execute()
    )

    return request
