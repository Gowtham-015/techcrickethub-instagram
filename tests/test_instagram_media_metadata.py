from instagram_media_metadata import MediaAsset


def test_media_asset_from_url():
    url = "https://cdn.example.com/assets/images/photo.jpg?version=1.2"
    asset = MediaAsset.from_url(
        url=url,
        media_type="IMAGE",
        content_type="image/jpeg",
        size_bytes=2048576,
        status_code=200,
    )

    assert asset.media_type == "IMAGE"
    assert asset.url == url
    assert asset.content_type == "image/jpeg"
    assert asset.extension == ".jpg"
    assert asset.source_host == "cdn.example.com"
    assert asset.is_https is True
    assert asset.size_bytes == 2048576
    assert asset.status_code == 200


def test_media_asset_http_scheme():
    asset = MediaAsset.from_url("http://example.com/video.mp4", media_type="REEL")
    assert asset.is_https is False
    assert asset.extension == ".mp4"
    assert asset.source_host == "example.com"
