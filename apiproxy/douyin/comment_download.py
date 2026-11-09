"""Save comment media in the format returned by the CDN."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from apiproxy.douyin import douyin_headers

_MIME_SUFFIXES = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
    "image/webp": ".webp", "image/avif": ".avif",
    "video/mp4": ".mp4", "video/webm": ".webm",
    "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/aac": ".aac",
    "audio/ogg": ".ogg", "audio/wav": ".wav",
}
_ALLOWED_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".mp4",
    ".webm", ".mp3", ".m4a", ".aac", ".ogg", ".wav", ".amr",
}


def _suffix(content_type: str, url: str, first_bytes: bytes) -> str:
    if first_bytes.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if first_bytes.startswith(b"RIFF") and first_bytes[8:12] == b"WEBP":
        return ".webp"
    if first_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if first_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if first_bytes[4:8] == b"ftyp":
        return ".mp4" if content_type.startswith("video/") else ".m4a" if content_type.startswith("audio/") else ".mp4"
    if first_bytes.startswith(b"ID3"):
        return ".mp3"
    if first_bytes.startswith(b"OggS"):
        return ".ogg"
    mime = content_type.split(";", 1)[0].lower().strip()
    if mime in _MIME_SUFFIXES:
        return _MIME_SUFFIXES[mime]
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in _ALLOWED_SUFFIXES:
        return ".jpg" if suffix == ".jpeg" else suffix
    fmt = (parse_qs(parsed.query).get("format") or [""])[0].lower()
    if "." + fmt in _ALLOWED_SUFFIXES:
        return "." + fmt
    guessed = mimetypes.guess_extension(mime) if mime else None
    return guessed if guessed in _ALLOWED_SUFFIXES else ".bin"


def download_comment_media(
    comments: list[dict], output_dir: Path,
    session: requests.Session | None = None,
    max_bytes: int = 100 * 1024 * 1024,
) -> tuple[int, int]:
    """Download each media item; keep its source URL and any error in JSON."""
    session = session or requests.Session()
    headers = {
        "User-Agent": douyin_headers["User-Agent"],
        "Referer": "https://www.douyin.com/",
    }
    downloaded = failures = 0
    for comment in comments:
        cid = comment.get("cid") or "unknown"
        safe_cid = "".join(char for char in str(cid) if char.isalnum()) or "unknown"
        for index, media in enumerate(comment.get("media") or [], 1):
            kind = "".join(char for char in media["kind"] if char.isalnum() or char == "_")
            destination_dir = output_dir / "media" / safe_cid
            destination_dir.mkdir(parents=True, exist_ok=True)
            existing = next(
                (path for path in destination_dir.glob(f"{kind}_{index}.*")
                 if path.is_file() and path.suffix != ".part"), None
            )
            if existing:
                media["local_path"] = existing.relative_to(output_dir).as_posix()
                downloaded += 1
                continue
            errors = []
            for url in media.get("urls") or [media["url"]]:
                if urlparse(url).scheme != "https":
                    errors.append("资源地址不是 HTTPS")
                    continue
                partial = None
                try:
                    with session.get(url, headers=headers, stream=True, timeout=20) as response:
                        response.raise_for_status()
                        mime = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                        if mime in ("text/html", "application/json", "text/plain"):
                            raise ValueError(f"CDN 返回 {mime}")
                        length = int(response.headers.get("Content-Length", "0") or "0")
                        if length > max_bytes:
                            raise ValueError("资源超过大小限制")
                        chunks = response.iter_content(chunk_size=65536)
                        first = next(chunks, b"")
                        if not first:
                            raise ValueError("资源为空")
                        suffix = _suffix(mime, url, first)
                        target = destination_dir / f"{kind}_{index}{suffix}"
                        partial = target.with_name(target.name + ".part")
                        size = len(first)
                        with partial.open("wb") as file:
                            file.write(first)
                            for chunk in chunks:
                                if chunk:
                                    size += len(chunk)
                                    if size > max_bytes:
                                        raise ValueError("资源超过大小限制")
                                    file.write(chunk)
                        partial.replace(target)
                        media["url"] = url
                        media["local_path"] = target.relative_to(output_dir).as_posix()
                        media["mime_type"] = mime
                        if suffix == ".gif":
                            media["animated"] = True
                        elif suffix == ".webp":
                            with target.open("rb") as file:
                                media["animated"] = b"ANIM" in file.read(65536)
                        downloaded += 1
                        break
                except (requests.RequestException, OSError, ValueError) as exc:
                    errors.append(type(exc).__name__)
                    if partial is not None:
                        partial.unlink(missing_ok=True)
            else:
                media["download_error"] = ", ".join(dict.fromkeys(errors)) or "未知错误"
                failures += 1
    return downloaded, failures
