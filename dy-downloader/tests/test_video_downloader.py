import pytest

from auth import CookieManager
from config import ConfigLoader
from control import QueueManager, RateLimiter, RetryHandler
from core.api_client import DouyinAPIClient
from core.video_downloader import VideoDownloader
from storage import FileManager


def _build_downloader(tmp_path):
    config = ConfigLoader()
    config.update(path=str(tmp_path))

    file_manager = FileManager(str(tmp_path))
    cookie_manager = CookieManager(str(tmp_path / '.cookies.json'))
    api_client = DouyinAPIClient({})

    downloader = VideoDownloader(
        config,
        api_client,
        file_manager,
        cookie_manager,
        database=None,
        rate_limiter=RateLimiter(max_per_second=5),
        retry_handler=RetryHandler(max_retries=1),
        queue_manager=QueueManager(max_workers=1),
    )

    return downloader, api_client


@pytest.mark.asyncio
async def test_video_downloader_skip_counts_total(tmp_path, monkeypatch):
    downloader, api_client = _build_downloader(tmp_path)

    async def _fake_should_download(self, _):
        return False

    downloader._should_download = _fake_should_download.__get__(downloader, VideoDownloader)

    result = await downloader.download({'aweme_id': '123'})

    assert result.total == 1
    assert result.skipped == 1
    assert result.success == 0
    assert result.failed == 0

    await api_client.close()


@pytest.mark.asyncio
async def test_build_no_watermark_url_signs_with_headers(tmp_path, monkeypatch):
    downloader, api_client = _build_downloader(tmp_path)

    signed_url = 'https://www.douyin.com/aweme/v1/play/?video_id=1&X-Bogus=signed'

    def _fake_sign(url: str):
        return signed_url, 'UnitTestAgent/1.0'

    monkeypatch.setattr(api_client, 'sign_url', _fake_sign)

    aweme = {
        'aweme_id': '1',
        'video': {
            'play_addr': {
                'url_list': [
                    'https://www.douyin.com/aweme/v1/play/?video_id=1&watermark=0'
                ]
            }
        },
    }

    url, headers = downloader._build_no_watermark_url(aweme)

    assert url == signed_url
    assert headers['User-Agent'] == 'UnitTestAgent/1.0'
    assert headers['Accept'] == '*/*'
    assert headers['Referer'].startswith('https://www.douyin.com')

    await api_client.close()


@pytest.mark.asyncio
async def test_gallery_downloads_still_and_live_clip(tmp_path, monkeypatch):
    downloader, api_client = _build_downloader(tmp_path)
    downloader.config.update(avatar=False, json=False)
    downloaded = []

    async def fake_session():
        return object()

    async def fake_download(url, save_path, session, headers=None):
        downloaded.append((url, save_path.name))
        return url != 'https://cdn.example/still.jpg'

    monkeypatch.setattr(api_client, 'get_session', fake_session)
    monkeypatch.setattr(downloader.file_manager, 'download_file', fake_download)

    aweme = {
        'aweme_id': '123',
        'desc': '实况图',
        'image_post_info': {'image_list': [
            {'url_list': ['https://cdn.example/still.jpg', 'https://backup.example/still.jpg'],
             'download_url_list': ['https://cdn.example/still-watermarked.jpg'],
             'video': {'play_addr': {'url_list': ['https://cdn.example/live.mp4']}}},
        ]},
    }
    assert downloader._detect_media_type(aweme) == 'gallery'
    assert await downloader._download_aweme_assets(aweme, 'author') is True
    assert downloaded == [
        ('https://cdn.example/still.jpg', '实况图_123_1.jpg'),
        ('https://backup.example/still.jpg', '实况图_123_1.jpg'),
        ('https://cdn.example/live.mp4', '实况图_123_1_live.mp4'),
    ]

    await api_client.close()
