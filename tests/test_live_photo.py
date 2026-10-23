"""Dependency-free checks for gallery and Live Photo payloads."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LivePhotoTest(unittest.TestCase):
    def test_old_and_new_gallery_payloads(self):
        for path in (ROOT / 'apiproxy/douyin/media.py',
                     ROOT / 'dy-downloader/utils/gallery_media.py'):
            with self.subTest(path=path):
                media = load_module('gallery_media_under_test', path)
                image = {
                    'url_list': ['https://cdn.example/still.webp'],
                    'video': {'play_addr': {'url_list': ['https://cdn.example/motion.mp4']}},
                }
                self.assertEqual(media.gallery_images({'images': [image]}), [image])
                self.assertEqual(media.gallery_images({
                    'image_post_info': {'image_list': [image]}
                }), [image])
                self.assertEqual(media.image_url(image), 'https://cdn.example/still.webp')
                self.assertEqual(media.live_photo_url(image), 'https://cdn.example/motion.mp4')
                self.assertEqual(media.image_suffix(media.image_url(image)), '.webp')

    def test_display_image_wins_over_watermarked_download_url(self):
        for path in (ROOT / 'apiproxy/douyin/media.py',
                     ROOT / 'dy-downloader/utils/gallery_media.py'):
            with self.subTest(path=path):
                media = load_module('gallery_media_under_test', path)
                image = {
                    'url_list': [
                        'https://cdn.example/no-watermark.webp',
                        'https://cdn-backup.example/no-watermark.webp',
                    ],
                    'download_url_list': ['https://cdn.example/watermarked.webp'],
                }
                self.assertEqual(
                    media.image_url(image), 'https://cdn.example/no-watermark.webp'
                )
                self.assertEqual(media.image_urls(image), image['url_list'])
                self.assertEqual(media.image_urls({
                    'download_url_list': ['https://cdn.example/watermarked.webp']
                }), [])

    def test_uri_only_motion_and_gif(self):
        for path in (ROOT / 'apiproxy/douyin/media.py',
                     ROOT / 'dy-downloader/utils/gallery_media.py'):
            with self.subTest(path=path):
                media = load_module('gallery_media_under_test', path)
                image = {
                    'url_list': ['https://cdn.example/animation.gif'],
                    'video': {'play_addr': {'uri': 'clip/123'}},
                }
                self.assertEqual(media.image_suffix(media.image_url(image)), '.gif')
                self.assertIn('video_id=clip%2F123', media.live_photo_url(image))
                self.assertIsNone(media.live_photo_url({'url_list': ['https://cdn.example/still.jpg']}))

    def test_legacy_result_keeps_nested_motion_address(self):
        media = load_module('apiproxy.douyin.media', ROOT / 'apiproxy/douyin/media.py')
        package = types.ModuleType('apiproxy')
        package.__path__ = []
        douyin_package = types.ModuleType('apiproxy.douyin')
        douyin_package.__path__ = []
        with patch.dict(sys.modules, {
            'apiproxy': package,
            'apiproxy.douyin': douyin_package,
            'apiproxy.douyin.media': media,
        }):
            result_module = load_module('legacy_result_under_test', ROOT / 'apiproxy/douyin/result.py')
            result = result_module.Result()
            image = {'url_list': ['https://cdn.example/still.jpg'],
                     'video': {'play_addr': {'url_list': ['https://cdn.example/live.mp4']}}}
            result.dataConvert(1, result.awemeDict, {
                'aweme_id': '123',
                'image_post_info': {'images': [image]},
            })
            self.assertEqual(result.awemeDict['images'][0]['video'], image['video'])


if __name__ == '__main__':
    unittest.main()
