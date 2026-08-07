"""Vinculacion y subida a YouTube por canal (portado de videos_automaticos).

Cada canal guarda sus credenciales en youtube_creds/channel_XXXX/:
- client_secret.json (subido por el usuario, del proyecto de Google)
- token.json (generado tras autorizar con Google)
"""
from __future__ import annotations

import json
import os
import urllib.parse
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]

# Google a veces devuelve los scopes en distinto formato.
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"


class YouTubeService:
    def __init__(self, channel_id: int, creds_base: Path) -> None:
        self.channel_id = channel_id
        self.creds_dir = creds_base / f"channel_{channel_id:04d}"
        self.creds_dir.mkdir(parents=True, exist_ok=True)
        self.token_path = self.creds_dir / "token.json"
        self.secret_path = self.creds_dir / "client_secret.json"

    # --- credenciales ---
    def has_secret(self) -> bool:
        return self.secret_path.exists()

    def save_secret(self, content: bytes) -> None:
        # Valida que sea un JSON de credenciales OAuth.
        data = json.loads(content.decode("utf-8"))
        if not (data.get("web") or data.get("installed")):
            raise ValueError("El client_secret.json no tiene la clave 'web' o 'installed'.")
        self.secret_path.write_bytes(content)

    def get_credentials(self) -> Credentials | None:
        creds = None
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            except Exception:
                return None
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    self.token_path.write_text(creds.to_json())
                except Exception:
                    if self.token_path.exists():
                        self.token_path.unlink()
                    return None
            else:
                return None
        return creds

    def is_authenticated(self) -> bool:
        return self.get_credentials() is not None

    def unlink(self) -> None:
        """Borra el token para forzar una nueva autorizacion (elegir otro canal)."""
        if self.token_path.exists():
            self.token_path.unlink()

    # --- flujo OAuth ---
    def get_auth_url(self, redirect_uri: str) -> str:
        if not self.secret_path.exists():
            raise FileNotFoundError("Falta client_secret.json en este canal.")
        with open(self.secret_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        web_data = data.get("web") or data.get("installed")
        params = {
            "client_id": web_data["client_id"],
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
            "response_type": "code",
            "access_type": "offline",
            # select_account + consent fuerza el selector de cuenta/canal (marca)
            # para elegir el canal de YouTube correcto cada vez.
            "prompt": "select_account consent",
            "include_granted_scopes": "true",
            "state": str(self.channel_id),
        }
        return f"{web_data['auth_uri']}?{urllib.parse.urlencode(params)}"

    def finish_oauth(self, code: str, redirect_uri: str) -> Credentials:
        flow = Flow.from_client_secrets_file(
            str(self.secret_path), scopes=SCOPES, redirect_uri=redirect_uri
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        self.token_path.write_text(creds.to_json())
        return creds

    # --- info y subida ---
    def get_channel_info(self) -> dict | None:
        creds = self.get_credentials()
        if not creds:
            return None
        youtube = build("youtube", "v3", credentials=creds)
        response = youtube.channels().list(part="snippet,statistics", mine=True).execute()
        items = response.get("items")
        return items[0] if items else None

    def upload_video(self, video_path: Path, metadata: dict[str, Any]) -> dict:
        creds = self.get_credentials()
        if not creds:
            raise RuntimeError("El canal no esta autenticado con YouTube.")
        youtube = build("youtube", "v3", credentials=creds)

        # Sanea los tags (limite 100 por tag, 500 en total).
        clean_tags: list[str] = []
        total_len = 0
        for raw in metadata.get("tags", "").split(","):
            tag = raw.replace("?", "").replace("¿", "").strip()
            if not tag:
                continue
            if len(tag) > 100:
                tag = tag[:97] + "..."
            if total_len + len(tag) + 1 < 500:
                clean_tags.append(tag)
                total_len += len(tag) + 1
            else:
                break

        body = {
            "snippet": {
                "title": metadata.get("title", "Untitled")[:100],
                "description": metadata.get("description", "")[:5000],
                "tags": clean_tags,
                "categoryId": metadata.get("category_id", "22"),
            },
            "status": {
                "privacyStatus": metadata.get("privacy_status", "private"),
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Subiendo a YouTube {int(status.progress() * 100)}%", flush=True)
        return response
