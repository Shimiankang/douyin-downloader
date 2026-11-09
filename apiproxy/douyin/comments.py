"""Fetch Douyin work comments and retain their structured media."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from apiproxy.common import utils
from apiproxy.douyin import douyin_headers
from apiproxy.douyin.urls import Urls


class CommentError(RuntimeError):
    """A comment API response cannot be used."""


def resolve_aweme_id(value: str, session: requests.Session | None = None) -> str:
    """Accept an aweme ID, a work URL, or a Douyin short share URL."""
    value = value.strip()
    if re.fullmatch(r"\d+", value):
        return value
    match = re.search(r"https?://[^\s<>]+", value)
    if not match:
        raise ValueError("请输入作品 ID 或抖音作品链接")
    url = match.group(0).rstrip("，。,)）")

    def parse(link: str) -> str | None:
        parts = urlparse(link)
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or not (
            host == "douyin.com" or host.endswith(".douyin.com")
            or host == "iesdouyin.com" or host.endswith(".iesdouyin.com")
        ):
            raise ValueError("仅支持抖音作品链接")
        modal = parse_qs(parts.query).get("modal_id", [])
        if modal and re.fullmatch(r"\d+", modal[0]):
            return modal[0]
        work = re.search(r"/(?:video|note|slides)/(\d+)(?:/|$)", parts.path)
        return work.group(1) if work else None

    aweme_id = parse(url)
    if aweme_id:
        return aweme_id
    if urlparse(url).hostname != "v.douyin.com":
        raise ValueError("链接中没有作品 ID")
    response = (session or requests).get(
        url, headers={"User-Agent": douyin_headers["User-Agent"]}, timeout=15
    )
    response.raise_for_status()
    aweme_id = parse(response.url)
    if not aweme_id:
        raise ValueError("短链接未跳转到作品页")
    return aweme_id


def _urls(value, depth: int = 0) -> list[str]:
    """Read CDN alternatives from one media object, without traversing user data."""
    if depth > 6:
        return []
    if isinstance(value, str):
        return [value] if value.startswith(("https://", "http://")) else []
    if isinstance(value, list):
        urls = [url for item in value for url in _urls(item, depth + 1)]
    elif isinstance(value, dict):
        preferred = (
            "url_list", "urls", "url", "play_addr", "download_addr",
            "play_url", "download_url", "origin_url", "animate_url",
            "static_url", "uri",
        )
        urls = [url for key in preferred if key in value
                for url in _urls(value[key], depth + 1)]
        if not urls:
            urls = [url for item in value.values()
                    for url in _urls(item, depth + 1)]
    else:
        return []
    return list(dict.fromkeys(urls))


def extract_media(comment: dict, emoji_lookup: dict[str, list[str]] | None = None) -> list[dict]:
    """Extract known media fields without mistaking author avatars for comments."""
    media: list[dict] = []
    seen: set[str] = set()

    def add(kind: str, field: str, value) -> None:
        urls = _urls(value)
        if not urls:
            return
        primary = urls[0]
        if primary in seen:
            return
        seen.add(primary)
        media.append({
            "kind": kind, "source_field": field, "url": primary,
            "urls": urls, "local_path": None,
        })

    for index, image in enumerate(comment.get("image_list") or []):
        if not isinstance(image, dict):
            add("image", f"image_list[{index}]", image)
            continue
        # The download URL may have a stamped watermark. Prefer the original.
        alternatives = [
            image.get(key) for key in
            ("origin_url", "medium_url", "crop_url", "thumb_url")
            if image.get(key)
        ]
        if not alternatives:
            alternatives = [image.get("download_url")]
        add("image", f"image_list[{index}]", alternatives)
        for field in ("animate_url", "video", "live_photo_url"):
            if image.get(field):
                add("animation", f"image_list[{index}].{field}", image[field])

    sticker = comment.get("sticker")
    if isinstance(sticker, dict):
        add("sticker_animation", "sticker.animate_url", sticker.get("animate_url"))
        add("sticker_image", "sticker.static_url", sticker.get("static_url"))
    elif sticker:
        add("sticker", "sticker", sticker)

    groups = {
        "emoji": ("decorated_emoji_info", "emoji_detail_list", "emoji_list", "emoji_info"),
        "audio": ("voice", "voice_info", "voice_url", "voice_comment",
                  "voice_message", "audio", "audio_info", "audio_url",
                  "audio_message"),
        "animation": ("gif", "gif_url", "animated_image", "animated_image_url"),
        "video": ("video_list", "video", "video_url"),
    }
    for kind, fields in groups.items():
        for field in fields:
            value = comment.get(field)
            if isinstance(value, list):
                for index, item in enumerate(value):
                    add(kind, f"{field}[{index}]", item)
            elif value:
                add(kind, field, value)

    # Keep newly introduced media fields usable without walking unrelated
    # objects such as user avatars or links embedded in comment text.
    known_fields = {"image_list", "sticker"}
    known_fields.update(field for fields in groups.values() for field in fields)
    for field, value in comment.items():
        if field in known_fields:
            continue
        name = field.lower()
        if any(word in name for word in ("voice", "audio", "sound")):
            kind = "audio"
        elif any(word in name for word in ("emoji", "sticker")):
            kind = "emoji"
        elif any(word in name for word in ("gif", "animate", "live_photo")):
            kind = "animation"
        elif "image" in name:
            kind = "image"
        elif "media" in name:
            kind = "media"
        else:
            continue
        if isinstance(value, list):
            for index, item in enumerate(value):
                add(kind, f"{field}[{index}]", item)
        elif value:
            add(kind, field, value)

    if emoji_lookup:
        for token in dict.fromkeys(re.findall(r"\[[^\[\]]{1,40}\]", comment.get("text") or "")):
            if token in emoji_lookup:
                add("emoji", f"text:{token}", emoji_lookup[token])
    return media


def normalize_comment(
    comment: dict, parent_cid: str | None = None,
    emoji_lookup: dict[str, list[str]] | None = None,
) -> dict:
    user = comment.get("user") or {}
    if not isinstance(user, dict):
        user = {}
    return {
        "cid": str(comment.get("cid") or ""),
        "aweme_id": str(comment.get("aweme_id") or ""),
        "parent_cid": parent_cid,
        "reply_to_cid": str(comment.get("reply_to_reply_id") or ""),
        "text": comment.get("text") or "",
        "create_time": comment.get("create_time"),
        "digg_count": comment.get("digg_count", 0),
        "reply_comment_total": comment.get("reply_comment_total", 0),
        "ip_label": comment.get("ip_label") or "",
        "user": {
            "uid": str(user.get("uid") or ""),
            "sec_uid": user.get("sec_uid") or "",
            "nickname": user.get("nickname") or "",
            "unique_id": user.get("unique_id") or "",
        },
        "media": extract_media(comment, emoji_lookup),
    }


class CommentClient:
    """Signed, paginated access to public work comments and their replies."""

    def __init__(
        self, cookie: str, session: requests.Session | None = None,
        interval: float = 0.5, timeout: float = 15,
    ) -> None:
        self.session = session or requests.Session()
        self.headers = dict(douyin_headers)
        if cookie:
            self.headers["Cookie"] = cookie
        self.urls = Urls()
        self.interval = max(0.0, interval)
        self.timeout = timeout
        self._last_request = 0.0
        self.warnings: list[str] = []
        self.reported_total: int | None = None

    def _get(self, endpoint: str, params: dict) -> dict:
        if self._last_request:
            time.sleep(max(0.0, self.interval - (time.monotonic() - self._last_request)))
        signed = utils.getXbogus(urlencode(params))
        try:
            response = self.session.get(
                endpoint + signed, headers=self.headers, timeout=self.timeout
            )
            self._last_request = time.monotonic()
            if response.status_code != 200:
                raise CommentError(f"评论接口 HTTP {response.status_code}")
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise CommentError(f"评论接口请求失败：{type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise CommentError("评论接口未返回 JSON 对象")
        if payload.get("status_code") != 0:
            raise CommentError(f"评论接口状态码：{payload.get('status_code')}")
        return payload

    def _iter_comments(self, aweme_id: str, parent_cid: str | None, limit: int):
        cursor = 0
        seen_cursors = {cursor}
        seen_cids: set[str] = set()
        yielded = 0
        while limit == 0 or yielded < limit:
            count = min(20, limit - yielded) if limit else 20
            if parent_cid:
                endpoint = self.urls.COMMENT_REPLY
                params = {
                    "item_id": aweme_id, "comment_id": parent_cid,
                    "cursor": cursor, "count": count, "item_type": 0,
                    "aid": 6383, "device_platform": "webapp",
                }
            else:
                endpoint = self.urls.COMMENT
                params = {
                    "aweme_id": aweme_id, "cursor": cursor, "count": count,
                    "item_type": 0, "aid": 6383, "device_platform": "webapp",
                }
            payload = self._get(endpoint, params)
            if parent_cid is None and self.reported_total is None:
                self.reported_total = payload.get("total")
            comments = payload.get("comments") or []
            if not isinstance(comments, list):
                raise CommentError("评论列表格式错误")
            for comment in comments:
                if not isinstance(comment, dict):
                    continue
                cid = str(comment.get("cid") or "")
                if cid and cid in seen_cids:
                    continue
                if cid:
                    seen_cids.add(cid)
                yield comment
                yielded += 1
                if limit and yielded >= limit:
                    return
            if not payload.get("has_more"):
                return
            next_cursor = payload.get("cursor")
            if not comments or next_cursor is None or next_cursor in seen_cursors:
                self.warnings.append(
                    f"评论分页在游标 {cursor} 停止：接口未提供新的评论或有效游标"
                )
                return
            cursor = next_cursor
            seen_cursors.add(cursor)

    def emoji_lookup(self) -> dict[str, list[str]]:
        """Map text tokens such as [笑哭] to their custom emoji images."""
        try:
            payload = self._get(
                self.urls.EMOJI_LIST, {"aid": 6383, "device_platform": "webapp"}
            )
        except CommentError as exc:
            self.warnings.append(f"自定义表情列表不可用：{exc}")
            return {}
        lookup = {}
        for emoji in payload.get("emoji_list") or []:
            if isinstance(emoji, dict) and isinstance(emoji.get("display_name"), str):
                urls = _urls(emoji.get("emoji_url"))
                if urls:
                    lookup[emoji["display_name"]] = urls
        return lookup

    def crawl(
        self, aweme_id: str, limit: int = 100, reply_limit: int = 100,
        include_replies: bool = True,
    ) -> tuple[list[dict], list[dict]]:
        """Return normalized comments and original response objects."""
        self.warnings.clear()
        self.reported_total = None
        raw: list[dict] = []
        entries: list[tuple[dict, str | None]] = []
        for comment in self._iter_comments(aweme_id, None, limit):
            cid = str(comment.get("cid") or "")
            raw.append({"parent_cid": None, "comment": comment})
            entries.append((comment, None))
            if include_replies and cid and comment.get("reply_comment_total", 0):
                try:
                    replies = list(self._iter_comments(aweme_id, cid, reply_limit))
                except CommentError as exc:
                    self.warnings.append(f"评论 {cid} 的回复获取失败：{exc}")
                    replies = []
                for reply in replies:
                    raw.append({"parent_cid": cid, "comment": reply})
                    entries.append((reply, cid))
        lookup = self.emoji_lookup() if any(
            "[" in (comment.get("text") or "") for comment, _ in entries
        ) else {}
        normalized = [
            normalize_comment(comment, parent, lookup) for comment, parent in entries
        ]
        return normalized, raw


def make_export(aweme_id: str, source: str, comments: list[dict],
                reported_total: int | None, warnings: list[str]) -> dict:
    return {
        "aweme_id": aweme_id,
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "reported_total": reported_total,
        "top_level_count": sum(item["parent_cid"] is None for item in comments),
        "reply_count": sum(item["parent_cid"] is not None for item in comments),
        "warnings": warnings,
        "comments": comments,
    }
