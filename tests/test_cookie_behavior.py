import json

from apiproxy.douyin.douyin import Douyin
from get_cookies_manual import validate_cookies


def test_missing_ms_token_is_not_treated_as_invalid_cookie(capsys):
    assert validate_cookies({
        'ttwid': 'example',
        'sessionid': 'example',
        'sessionid_ss': 'example',
        'passport_csrf_token': 'example',
    }) is True
    assert '这不代表 Cookie 无效' in capsys.readouterr().out


def test_user_post_403_uses_open_origin_fallback(monkeypatch):
    requests_seen = []

    class Response:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self.text = json.dumps(payload) if payload is not None else ''

    def fake_get(url, headers, timeout):
        requests_seen.append((url, headers))
        if len(requests_seen) == 1:
            return Response(403)
        return Response(200, {
            'status_code': 0,
            'aweme_list': [{'aweme_id': '123', 'create_time': 1700000000}],
            'has_more': 0,
            'max_cursor': 0,
        })

    monkeypatch.setattr('apiproxy.douyin.douyin.requests.get', fake_get)
    downloader = Douyin(database=False)
    monkeypatch.setattr(downloader, '_convert_aweme_data', lambda item: item)

    items = downloader.getUserInfo('sample-user', mode='post', count=1, number=1)
    assert len(items) == 1
    assert requests_seen[1][1]['Origin'] == 'https://open.douyin.com'
    assert 'sec_user_id=sample-user' in requests_seen[1][0]
