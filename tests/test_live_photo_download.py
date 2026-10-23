import asyncio
import shutil
import uuid
from pathlib import Path

import pytest
from DouYinCommand import configModel, handle_aweme_download
from apiproxy.douyin.douyin import Douyin
from apiproxy.douyin.download import Download
from apiproxy.douyin.result import Result
from downloader import UnifiedDownloader


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace_tmp():
    path = (ROOT / ('test-live-photo-' + uuid.uuid4().hex)).resolve()
    assert path.is_relative_to(ROOT.resolve())
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def live_photo_aweme():
    raw = {
        'aweme_id': '123',
        'desc': 'Live Photo',
        'image_post_info': {'images': [{
            'url_list': ['https://cdn.example/still.jpg'],
            'video': {'play_addr': {'url_list': ['https://cdn.example/motion.mp4']}},
        }]},
    }
    result = Result()
    result.dataConvert(1, result.awemeDict, raw)
    return result.awemeDict


def test_legacy_downloader_keeps_still_and_motion(workspace_tmp, monkeypatch):
    downloader = Download(music=False, cover=False, avatar=False, resjson=False)
    calls = []

    def fake_download(url, path, desc):
        calls.append((url, path.name))
        return True

    monkeypatch.setattr(downloader, '_download_media', fake_download)
    downloader._download_media_files(live_photo_aweme(), workspace_tmp, 'work', 'work')

    assert calls == [
        ('https://cdn.example/still.jpg', 'work_image_1.jpg'),
        ('https://cdn.example/motion.mp4', 'work_image_1_live.mp4'),
    ]


def test_legacy_downloader_tries_next_clean_image_cdn(workspace_tmp, monkeypatch):
    downloader = Download(music=False, cover=False, avatar=False, resjson=False)
    aweme = live_photo_aweme()
    aweme['images'][0]['url_list'].append('https://backup.example/still.jpg')
    aweme['images'][0]['download_url_list'] = ['https://cdn.example/stamped.jpg']
    calls = []

    def fake_download(url, path, desc):
        calls.append(url)
        return url != 'https://cdn.example/still.jpg'

    monkeypatch.setattr(downloader, '_download_media', fake_download)
    downloader._download_media_files(aweme, workspace_tmp, 'work', 'work')
    assert calls == [
        'https://cdn.example/still.jpg',
        'https://backup.example/still.jpg',
        'https://cdn.example/motion.mp4',
    ]


def test_legacy_single_work_accepts_gallery_without_video_url(workspace_tmp, monkeypatch):
    class FakeDouyin:
        def getAwemeInfo(self, key):
            return live_photo_aweme()

    class FakeDownload:
        def __init__(self):
            self.items = []

        def userDownload(self, awemeList, savePath):
            self.items.extend(awemeList)
            return len(awemeList)

    monkeypatch.setitem(configModel, 'path', str(workspace_tmp))
    downloader = FakeDownload()
    assert handle_aweme_download(FakeDouyin(), downloader, '123') is True
    assert len(downloader.items) == 1


def test_modal_url_is_a_single_work():
    url = ('https://www.douyin.com/user/example?from_tab_name=main'
           '&modal_id=7635932187272477412')
    assert Douyin(database=False).getKey(url) == ('aweme', '7635932187272477412')
    downloader = object.__new__(UnifiedDownloader)
    assert downloader.detect_content_type(url) == 'video'
    assert downloader.extract_id_from_url(url) == '7635932187272477412'


def test_detail_api_uses_open_origin_fallback_for_live_photo(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, headers, timeout):
        calls.append((url, headers))
        if len(calls) == 1:
            return Response(403)
        return Response(200, {'status_code': 0, 'aweme_detail': {
            'aweme_id': '123',
            'images': [{
                'url_list': ['https://cdn.example/still.jpg'],
                'video': {'play_addr': {'url_list': ['https://cdn.example/live.mp4']}},
            }],
        }})

    monkeypatch.setattr('apiproxy.douyin.douyin.requests.get', fake_get)
    info = Douyin(database=False)._try_detail_api('123')
    assert info['awemeType'] == 1
    assert info['images'][0]['video']['play_addr']['url_list'][0].endswith('live.mp4')
    assert calls[1][1]['Origin'] == 'https://open.douyin.com'


def test_unified_downloader_keeps_still_and_motion(workspace_tmp, monkeypatch):
    downloader = object.__new__(UnifiedDownloader)
    downloader.config = {'cover': False, 'json': False, 'music': False}
    downloader.save_path = workspace_tmp
    calls = []

    async def fake_download(url, path, quiet=False):
        calls.append((url, path.name))
        return True

    monkeypatch.setattr(downloader, '_download_file', fake_download)
    assert asyncio.run(downloader._download_media_files(live_photo_aweme())) is True
    assert calls == [
        ('https://cdn.example/still.jpg', 'image_1.jpg'),
        ('https://cdn.example/motion.mp4', 'image_1_live.mp4'),
    ]


def test_unified_downloader_tries_next_clean_image_cdn(workspace_tmp, monkeypatch):
    downloader = object.__new__(UnifiedDownloader)
    downloader.config = {'cover': False, 'json': False, 'music': False}
    downloader.save_path = workspace_tmp
    aweme = live_photo_aweme()
    aweme['images'][0]['url_list'].append('https://backup.example/still.jpg')
    aweme['images'][0]['download_url_list'] = ['https://cdn.example/stamped.jpg']
    calls = []

    async def fake_download(url, path, quiet=False):
        calls.append(url)
        return url != 'https://cdn.example/still.jpg'

    monkeypatch.setattr(downloader, '_download_file', fake_download)
    assert asyncio.run(downloader._download_media_files(aweme)) is True
    assert calls == [
        'https://cdn.example/still.jpg',
        'https://backup.example/still.jpg',
        'https://cdn.example/motion.mp4',
    ]


def test_legacy_partial_file_restarts_when_range_is_ignored(workspace_tmp, monkeypatch):
    downloader = Download(music=False, cover=False, avatar=False, resjson=False)
    final_path = workspace_tmp / 'live.mp4'
    partial_path = workspace_tmp / 'live.mp4.part'
    partial_path.write_bytes(b'old')

    class Response:
        status_code = 200
        headers = {'content-length': '3'}

        def iter_content(self, chunk_size):
            yield b'new'

    monkeypatch.setattr('apiproxy.douyin.download.requests.get', lambda *a, **kw: Response())
    assert downloader._download_media('https://cdn.example/live.mp4', final_path, 'live')
    assert final_path.read_bytes() == b'new'
    assert not partial_path.exists()
