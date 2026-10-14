
from app.dataset import _parse_x_operations, normalize_x, x_timeline_photos


def test_normalize_x_variants():
    assert normalize_x("@Some_User") == "Some_User"
    assert normalize_x("https://x.com/Some_User") == "Some_User"
    assert normalize_x("https://twitter.com/Some_User/") == "Some_User"
    assert normalize_x("x.com/Some_User?ref=abc") == "Some_User"
    import pytest

    with pytest.raises(ValueError):
        normalize_x("https://example.com/Some_User")


def test_parse_x_operations_from_bundle():
    js = (
        'n={queryId:"abc-123_XY",operationName:"UserByScreenName",metadata:{featureSwitches:["hidden_x","with_y"],'
        'fieldToggles:["withAuxiliaryUserLabels"]}};'
        'm={queryId:"def-456_ZW",operationName:"UserTweets",metadata:{featureSwitches:["with_z"],fieldToggles:[]}}'
    )
    operations = _parse_x_operations(js)
    assert operations["UserByScreenName"]["queryId"] == "abc-123_XY"
    assert operations["UserByScreenName"]["features"] == {"hidden_x": True, "with_y": True}
    assert operations["UserByScreenName"]["fieldToggles"] == {"withAuxiliaryUserLabels": True}
    assert operations["UserTweets"]["queryId"] == "def-456_ZW"


def _tweet(photo_url, *, retweet=False):
    legacy = {
        "extended_entities": {"media": [{"type": "photo", "media_url_https": photo_url}]},
        "in_reply_to_status_id_str": None,
        "id_str": "1",
    }
    if retweet:
        legacy["retweeted_status_result"] = {"result": {}}
    return {"legacy": legacy}


def test_x_timeline_photos_extracts_photos_and_cursor():
    data = {
        "data": {
            "user": {
                "result": {
                    "timeline_v2": {
                        "timeline": {
                            "instructions": [
                                {
                                    "entries": [
                                        {
                                            "entryId": "tweet-1",
                                            "content": {"itemContent": {"tweet_results": {"result": _tweet("https://pbs.twimg.com/media/A.jpg")}}},
                                        },
                                        {
                                            "entryId": "tweet-2",
                                            "content": {"itemContent": {"tweet_results": {"result": _tweet("https://pbs.twimg.com/media/B.jpg", retweet=True)}}},
                                        },
                                        {
                                            "entryId": "cursor-bottom-1",
                                            "content": {"cursorType": "Bottom", "value": "CURSOR123"},
                                        },
                                    ]
                                }
                            ]
                        }
                    }
                }
            }
        }
    }
    urls, cursor = x_timeline_photos(data, 10)
    assert urls == ["https://pbs.twimg.com/media/A.jpg?name=large"]
    assert cursor == "CURSOR123"
    assert x_timeline_photos(data, 1)[0] == urls


def test_dataset_source_kind_x_accepted(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    key = {"X-API-Key": "test-key"}
    monkeypatch.setattr("app.dataset.import_x", lambda source, reference, limit, db: 0)
    response = client.post(
        "/api/dataset/sources",
        json={"name": "X profile", "kind": "x", "reference": "https://x.com/somebody", "classify": False},
        headers=key,
    )
    assert response.status_code == 201, response.text
    assert response.json()["kind"] == "x"


def test_normalize_x_post_links():
    from app.dataset import normalize_x_reference

    assert normalize_x_reference("@Some_User") == ("Some_User", None)
    assert normalize_x_reference("https://x.com/user/media") == ("user", None)
    assert normalize_x_reference("https://x.com/user/status/1234567890") == ("user", "1234567890")
    assert normalize_x_reference("x.com/user/status/42?s=20") == ("user", "42")


def test_nextcloud_reference_and_propfind_parser():
    from app.dataset import _parse_nextcloud_propfind, parse_nextcloud_reference

    base, token, folder = parse_nextcloud_reference("https://cloud.example.com/s/AbC123")
    assert base == "https://cloud.example.com/s/AbC123" and token == "AbC123" and folder == ""
    base, token, folder = parse_nextcloud_reference("https://cloud.example.com/s/AbC123?path=%2Fphotos%2Fnikita")
    assert folder == "photos/nikita"
    import pytest
    with pytest.raises(ValueError):
        parse_nextcloud_reference("https://example.com/other")

    xml = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response><d:href>/public.php/dav/files/T/</d:href><d:propstat><d:prop><d:collection/></d:prop></d:propstat></d:response>
  <d:response><d:href>/public.php/dav/files/T/a.jpg</d:href><d:propstat><d:prop><d:getcontentlength>1234</d:getcontentlength></d:prop></d:propstat></d:response>
  <d:response><d:href>/public.php/dav/files/T/sub/</d:href><d:propstat><d:prop><d:collection/></d:prop></d:propstat></d:response>
</d:multistatus>"""
    entries = _parse_nextcloud_propfind(xml, "/public.php/dav/files/T", "https://cloud.example.com")
    assert [entry["path"] for entry in entries] == ["a.jpg", "sub"]
    image = entries[0]
    assert image["suffix"] == ".jpg" and image["size"] == 1234 and not image["is_dir"]
    assert image["url"].endswith("/public.php/dav/files/T/a.jpg")
    assert entries[1]["is_dir"] is True


def test_dataset_source_kind_nextcloud_accepted(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr("app.dataset.import_nextcloud", lambda source, reference, limit, db: 0)
    client = TestClient(app, headers={"X-API-Key": "test-key"})
    response = client.post(
        "/api/dataset/sources",
        json={"name": "Nextcloud", "kind": "nextcloud", "reference": "https://cloud.example.com/s/AbC123", "classify": False},
    )
    assert response.status_code == 201, response.text
    assert response.json()["kind"] == "nextcloud"
