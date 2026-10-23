from core.url_parser import URLParser


def test_parse_video_url():
    url = "https://www.douyin.com/video/7320876060210373923"
    parsed = URLParser.parse(url)

    assert parsed is not None
    assert parsed['type'] == 'video'
    assert parsed['aweme_id'] == '7320876060210373923'


def test_parse_gallery_url_sets_aweme_id():
    url = "https://www.douyin.com/note/7320876060210373923"
    parsed = URLParser.parse(url)

    assert parsed is not None
    assert parsed['type'] == 'gallery'
    assert parsed['aweme_id'] == '7320876060210373923'
    assert parsed['note_id'] == '7320876060210373923'


def test_parse_unsupported_url_returns_none():
    url = "https://www.douyin.com/music/123456"
    assert URLParser.parse(url) is None


def test_parse_user_modal_as_single_work():
    url = ('https://www.douyin.com/user/example?from_tab_name=main'
           '&modal_id=7635932187272477412')
    parsed = URLParser.parse(url)
    assert parsed['type'] == 'video'
    assert parsed['aweme_id'] == '7635932187272477412'
