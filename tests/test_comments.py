from urllib.parse import parse_qs, urlparse

import pytest

from apiproxy.douyin import comments as module
from apiproxy.douyin.comment_download import download_comment_media


def test_resolve_aweme_id_from_modal_and_work_url():
    assert module.resolve_aweme_id(
        "https://www.douyin.com/user/self?modal_id=7677649625825676582"
    ) == "7677649625825676582"
    assert module.resolve_aweme_id(
        "https://www.douyin.com/note/1234567890123456789"
    ) == "1234567890123456789"
    with pytest.raises(ValueError):
        module.resolve_aweme_id("https://example.com/video/123")


def test_extract_comment_image_sticker_voice_and_emoji():
    comment = {
        "text": "你好 [笑哭] 😀",
        "user": {"avatar_thumb": {"url_list": ["https://cdn/user.jpg"]}},
        "image_list": [{
            "origin_url": {"url_list": ["https://cdn/original.gif"]},
            "download_url": {"url_list": ["https://cdn/watermarked.jpg"]},
        }],
        "sticker": {
            "animate_url": {"url_list": ["https://cdn/sticker.webp"]},
            "static_url": {"url_list": ["https://cdn/sticker.png"]},
        },
        "voice_comment_info": {"play_addr": {"url_list": ["https://cdn/voice.mp3"]}},
    }
    media = module.extract_media(comment, {"[笑哭]": ["https://cdn/emoji.png"]})
    assert [item["kind"] for item in media] == [
        "image", "sticker_animation", "sticker_image", "audio", "emoji",
    ]
    assert media[0]["url"] == "https://cdn/original.gif"
    assert "https://cdn/watermarked.jpg" not in media[0]["urls"]
    assert all("user.jpg" not in item["url"] for item in media)
    normalized = module.normalize_comment(comment)
    assert normalized["text"] == "你好 [笑哭] 😀"


class JsonResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class CommentSession:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return JsonResponse(self.payloads.pop(0))


def test_crawl_pages_replies_and_custom_emoji(monkeypatch):
    monkeypatch.setattr(module.utils, "getXbogus", lambda payload: payload)
    session = CommentSession([
        {
            "status_code": 0, "total": 2, "has_more": 1, "cursor": 20,
            "comments": [{"cid": "1", "aweme_id": "123", "text": "hi [笑哭]",
                          "reply_comment_total": 1}],
        },
        {
            "status_code": 0, "has_more": 0, "cursor": 0,
            "comments": [{"cid": "3", "aweme_id": "123", "text": "reply"}],
        },
        {
            "status_code": 0, "has_more": 0, "cursor": 40,
            "comments": [{"cid": "2", "aweme_id": "123", "text": "second"}],
        },
        {
            "status_code": 0,
            "emoji_list": [{
                "display_name": "[笑哭]",
                "emoji_url": {"url_list": ["https://cdn/emoji.gif"]},
            }],
        },
    ])
    client = module.CommentClient("ttwid=test", session=session, interval=0)
    comments, raw = client.crawl("123", limit=10)
    assert [item["cid"] for item in comments] == ["1", "3", "2"]
    assert comments[1]["parent_cid"] == "1"
    assert comments[0]["media"][0]["kind"] == "emoji"
    assert len(raw) == 3
    assert client.reported_total == 2
    assert "comment_id=1" in session.calls[1][0]
    assert parse_qs(urlparse(session.calls[2][0]).query)["cursor"] == ["20"]
    assert all("Cookie" in kwargs["headers"] for _, kwargs in session.calls)


def test_stops_repeated_cursor_without_loop(monkeypatch):
    monkeypatch.setattr(module.utils, "getXbogus", lambda payload: payload)
    session = CommentSession([{
        "status_code": 0, "has_more": 1, "cursor": 0,
        "comments": [{"cid": "1", "text": "hello"}],
    }])
    client = module.CommentClient("", session=session, interval=0)
    comments, _ = client.crawl("123", include_replies=False)
    assert len(comments) == 1
    assert len(session.calls) == 1
    assert client.warnings


class BinaryResponse:
    def __init__(self, data, mime):
        self.data = data
        self.headers = {"Content-Type": mime, "Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield self.data


class BinarySession:
    def get(self, url, **kwargs):
        assert "Cookie" not in kwargs["headers"]
        return BinaryResponse(b"GIF89a" + b"\0" * 16, "image/gif")


def test_download_media_keeps_animated_format(tmp_path):
    comments = [{
        "cid": "42",
        "media": [{
            "kind": "sticker_animation", "url": "https://cdn/sticker",
            "urls": ["https://cdn/sticker"], "local_path": None,
        }],
    }]
    downloaded, failures = download_comment_media(
        comments, tmp_path, session=BinarySession()
    )
    assert (downloaded, failures) == (1, 0)
    item = comments[0]["media"][0]
    assert item["local_path"].endswith(".gif")
    assert item["animated"] is True
    assert (tmp_path / item["local_path"]).read_bytes().startswith(b"GIF89a")


class EmptyBodyResponse:
    status_code = 200
    text = ""

    def raise_for_status(self):
        pass

    def json(self):
        import json
        return json.loads(self.text)


def test_reuses_complete_embedded_replies_without_calling_reply_api(monkeypatch):
    monkeypatch.setattr(module.utils, "getXbogus", lambda payload: payload)
    session = CommentSession([
        {
            "status_code": 0, "total": 3, "has_more": 0, "cursor": 0,
            "comments": [{
                "cid": "10", "aweme_id": "123", "text": "主评论",
                "reply_comment_total": 2,
                "reply_comment": [
                    {"cid": "11", "aweme_id": "123", "text": "回复1"},
                    {"cid": "12", "aweme_id": "123", "text": "回复2", "reply_to_reply_id": "11"},
                ],
            }],
        },
    ])
    client = module.CommentClient("ttwid=test", session=session, interval=0)
    comments, raw = client.crawl("123", limit=10, reply_limit=10)
    assert [item["cid"] for item in comments] == ["10", "11", "12"]
    assert comments[1]["parent_cid"] == "10"
    assert comments[2]["reply_to_cid"] == "11"
    assert len(raw) == 3
    assert len(session.calls) == 1
    assert not client.warnings


def test_falls_back_to_embedded_replies_when_reply_api_returns_empty_body(monkeypatch):
    monkeypatch.setattr(module.utils, "getXbogus", lambda payload: payload)

    class FallbackSession:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if "/comment/list/reply/" in url:
                return EmptyBodyResponse()
            return JsonResponse({
                "status_code": 0, "total": 4, "has_more": 0, "cursor": 0,
                "comments": [{
                    "cid": "20", "aweme_id": "123", "text": "主评论",
                    "reply_comment_total": 3,
                    "reply_comment": [
                        {"cid": "21", "aweme_id": "123", "text": "内嵌回复"},
                    ],
                }],
            })

    session = FallbackSession()
    client = module.CommentClient("ttwid=test", session=session, interval=0)
    comments, raw = client.crawl("123", limit=10, reply_limit=10)
    assert [item["cid"] for item in comments] == ["20", "21"]
    assert comments[1]["parent_cid"] == "20"
    assert len(raw) == 2
    assert len(session.calls) == 2
    assert len(client.warnings) == 1
    assert "空响应" in client.warnings[0]
    assert "1/3" in client.warnings[0]


def test_embedded_replies_respect_reply_limit(monkeypatch):
    monkeypatch.setattr(module.utils, "getXbogus", lambda payload: payload)
    session = CommentSession([
        {
            "status_code": 0, "total": 6, "has_more": 0, "cursor": 0,
            "comments": [{
                "cid": "30", "aweme_id": "123", "text": "主评论",
                "reply_comment_total": 5,
                "reply_comment": [
                    {"cid": "31", "aweme_id": "123", "text": "回复1"},
                    {"cid": "32", "aweme_id": "123", "text": "回复2"},
                ],
            }],
        },
    ])
    client = module.CommentClient("ttwid=test", session=session, interval=0)
    comments, _ = client.crawl("123", limit=10, reply_limit=1)
    assert [item["cid"] for item in comments] == ["30", "31"]
    assert len(session.calls) == 1
    assert not client.warnings
