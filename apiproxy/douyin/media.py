"""Extract still images and motion clips from Douyin gallery entries."""

from urllib.parse import parse_qs, quote, urlparse


def gallery_images(aweme):
    """Return the first populated gallery list in old or new API responses."""
    image_post = aweme.get("image_post_info") or {}
    for source in (image_post, aweme):
        if not isinstance(source, dict):
            continue
        for key in ("images", "image_list"):
            images = source.get(key)
            if isinstance(images, list) and images:
                return images
    return []


def _first_url(value):
    if isinstance(value, str):
        return value if value.startswith(("https://", "http://")) else None
    if isinstance(value, list):
        for item in value:
            url = _first_url(item)
            if url:
                return url
    if isinstance(value, dict):
        for key in ("url_list", "download_url_list", "url", "download_url",
                    "download_addr", "play_addr", "play_addr_h264",
                    "play_addr_lowbr"):
            url = _first_url(value.get(key))
            if url:
                return url
    return None


def image_url(image):
    urls = image_urls(image)
    return urls[0] if urls else None


def image_urls(image):
    """Return clean image CDN alternatives without stamped download URLs."""
    if not isinstance(image, dict):
        url = _first_url(image)
        return [url] if url else []
    # download_url_list/download_url can have a visible Douyin watermark.
    # Missing clean fields should fail explicitly instead of saving a stamp.
    for key in ("url_list", "origin_image", "display_image"):
        value = image.get(key)
        if isinstance(value, list):
            urls = [_first_url(item) for item in value]
        else:
            nested = value.get("url_list") if isinstance(value, dict) else value
            urls = [_first_url(item) for item in nested] if isinstance(nested, list) else [_first_url(nested)]
        urls = list(dict.fromkeys(url for url in urls if url))
        if urls:
            return urls
    return []


def live_photo_url(image):
    """Read the motion MP4 attached to one image, if present."""
    if not isinstance(image, dict):
        return None
    for key in ("live_photo_url", "live_url_list", "video",
                "video_play_addr", "video_download_addr"):
        value = image.get(key)
        if not value:
            continue
        if key == "video" and isinstance(value, dict):
            for address in ("play_addr", "play_addr_h264", "play_addr_lowbr",
                            "download_addr", "url_list"):
                url = _first_url(value.get(address))
                if url:
                    return url
            addresses = (value.get("play_addr"), value.get("play_addr_h264"),
                         value.get("play_addr_lowbr"), value.get("download_addr"))
        else:
            url = _first_url(value)
            if url:
                return url
            addresses = (value,)
        for address in addresses:
            if isinstance(address, dict) and address.get("uri"):
                return ("https://www.iesdouyin.com/aweme/v1/play/?video_id="
                        + quote(str(address["uri"]), safe="") + "&ratio=1080p")
    return None


def image_suffix(url, default=".jpeg"):
    """Keep GIF/WebP/PNG files in their actual format when identifiable."""
    parsed = urlparse(url)
    extension = parsed.path.lower().rsplit(".", 1)[-1]
    if extension in ("gif", "webp", "png", "jpg", "jpeg"):
        return ".jpg" if extension == "jpg" else "." + extension
    fmt = (parse_qs(parsed.query).get("format") or [""])[0].lower()
    return "." + fmt if fmt in ("gif", "webp", "png", "jpg", "jpeg") else default
