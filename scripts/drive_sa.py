"""
Drive vía service account (API directa) — para archivos grandes.

El conector nativo de Drive de Claude Code tiene límites (~6MB descarga,
subida solo inline). Estos helpers usan la Google Drive API directa con
un service account, sin límites de tamaño.

SETUP (una vez): ver README sección "Service account".
El setup script del entorno decodifica el secret GDRIVE_SA_B64 a
/workspace/sa.json antes de que arranque Claude Code.
"""

import os
import sys
import io
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "config"))
from config import GOOGLE_DRIVE_CREDENTIALS_PATH

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

logger = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/drive"]
_service = None


def get_service():
    global _service
    if _service is None:
        if not os.path.exists(GOOGLE_DRIVE_CREDENTIALS_PATH):
            raise RuntimeError(
                f"No existe {GOOGLE_DRIVE_CREDENTIALS_PATH}. El setup script del "
                f"entorno debe decodificar el secret GDRIVE_SA_B64 a ese archivo."
            )
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=SCOPES
        )
        _service = build("drive", "v3", credentials=creds)
    return _service


def buscar_carpeta(nombre: str, parent_id: str = None, crear: bool = False) -> str:
    service = get_service()
    query = (
        f"name='{nombre}' and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"
    res = service.files().list(q=query, fields="files(id,name)").execute()
    items = res.get("files", [])
    if items:
        return items[0]["id"]
    if not crear:
        raise RuntimeError(
            f"Carpeta '{nombre}' no encontrada en Drive. Verificá que exista y "
            f"que esté compartida (rol Editor) con el email del service account."
        )
    meta = {"name": nombre, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    carpeta = service.files().create(body=meta, fields="id").execute()
    logger.info(f"Carpeta creada en Drive: {nombre}")
    return carpeta["id"]


def listar_videos(folder_id: str) -> list[dict]:
    service = get_service()
    query = (
        f"'{folder_id}' in parents and trashed=false "
        f"and mimeType != 'application/vnd.google-apps.folder'"
    )
    res = service.files().list(
        q=query, fields="files(id,name,size)", pageSize=1000
    ).execute()
    archivos = res.get("files", [])
    return [
        a for a in archivos
        if a["name"].lower().endswith((".mp4", ".mov", ".mkv"))
    ]


def descargar(file_id: str, destino: str):
    service = get_service()
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(destino, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=50 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    logger.info(f"Descargado: {os.path.basename(destino)}")


def subir(local_path: str, nombre: str, folder_id: str) -> str:
    service = get_service()
    mimetype = "audio/mpeg" if nombre.lower().endswith(".mp3") else "video/mp4"
    media = MediaFileUpload(local_path, mimetype=mimetype, resumable=True,
                            chunksize=50 * 1024 * 1024)
    meta = {"name": nombre, "parents": [folder_id]}
    f = service.files().create(body=meta, media_body=media, fields="id").execute()
    logger.info(f"Subido a Drive: {nombre}")
    return f["id"]
