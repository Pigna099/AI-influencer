"""Image dataset pipeline: importers, rich vision descriptions, export and profile synthesis."""

import base64
import io
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import httpx
from PIL import Image
from sqlalchemy import delete, func, select

from .char_schemas import CharacterProfile
from .config import settings
from .db import DatasetImage, DatasetSource, ExecutionJob, Session, now
from .image_library import embed_library_text
from .integrations.text import OllamaNotAvailable, chat
from .jobs import create_job, finish_job, start_job, update_progress

logger = logging.getLogger(__name__)
CLASSIFY_STALE_SECONDS = 600

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v"}
TELEGRAM_IMAGE = re.compile(r"background-image:url\('([^']+)'\)")
TELEGRAM_VIDEO = re.compile(
    r"tgme_widget_message_video_thumb[^>]*background-image:url\('([^']+)'\)[\s\S]{0,6000}?<video[^>]+src=\"([^\"]+)\""
)
TELEGRAM_BEFORE = re.compile(r"[?&]before=(\d+)")
TELEGRAM_CDN = re.compile(r"^https?://cdn[^/]*\.(telesco\.pe|telegram\.org)/", re.IGNORECASE)

DESCRIBE_FIELDS = (
    "caption",
    "pose",
    "setting",
    "lighting",
    "scene",
    "outfit",
    "body",
    "skin",
    "camera",
    "mood",
    "art_style",
)
DESCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        **{field: {"type": "string"} for field in DESCRIBE_FIELDS},
        "minor_apparent": {"type": "boolean"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [*DESCRIBE_FIELDS, "minor_apparent", "tags"],
    "additionalProperties": False,
}


def _cdn_url(url: str) -> str | None:
    """Normalize protocol-relative URLs and keep only Telegram CDN media (skip emoji assets)."""
    if url.startswith("//"):
        url = f"https:{url}"
    return url if TELEGRAM_CDN.match(url) else None


def parse_telegram_page(html: str) -> dict:
    """Extract photo URLs, video entries (url + thumbnail) and the pagination cursor."""
    videos = []
    video_thumbs = set()
    for thumb, video in TELEGRAM_VIDEO.findall(html):
        video_url = _cdn_url(video.replace("\\/", "/"))
        if video_url is None:
            continue
        thumb_url = _cdn_url(thumb.replace("\\/", "/"))
        videos.append({"url": video_url, "thumb": thumb_url})
        if thumb_url:
            video_thumbs.add(thumb_url)
    images = []
    for url in TELEGRAM_IMAGE.findall(html):
        normalized = _cdn_url(url)
        if normalized and normalized not in video_thumbs:
            images.append(normalized)
    before_values = [int(value) for value in TELEGRAM_BEFORE.findall(html)]
    return {"images": images, "videos": videos, "before": min(before_values) if before_values else None}


def _source_dir(source_id: str) -> Path:
    path = (settings.dataset_dir / source_id).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _suffix(content_type: str | None, data: bytes) -> str:
    mapping = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    if content_type and content_type.split(";")[0].strip().lower() in mapping:
        return mapping[content_type.split(";")[0].strip().lower()]
    try:
        with Image.open(io.BytesIO(data)) as image:
            return f".{image.format.lower()}" if image.format else ".jpg"
    except OSError:
        return ".jpg"


def download_media(url: str, kind: str = "image") -> tuple[bytes, str] | None:
    limit = settings.dataset_video_max_bytes if kind == "video" else settings.dataset_download_max_bytes
    try:
        with httpx.Client(timeout=120 if kind == "video" else 30, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "Mozilla/5.0 (dataset-importer)"})
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        allowed = ("video/", "application/octet-stream") if kind == "video" else ("image/",)
        if not content_type.startswith(allowed):
            return None
        data = response.content
        if len(data) > limit:
            return None
        suffix = _suffix(content_type, data) if kind == "image" else ".mp4"
        return data, suffix
    except (httpx.HTTPError, OSError):
        return None


def download_image(url: str) -> tuple[bytes, str] | None:
    return download_media(url, "image")


def store_media(
    db,
    source: DatasetSource,
    data: bytes,
    suffix: str,
    kind: str = "image",
    thumb: tuple[bytes, str] | None = None,
) -> DatasetImage | None:
    import hashlib

    digest = hashlib.sha256(data).hexdigest()
    exists = db.scalar(
        select(DatasetImage.id).where(DatasetImage.source_id == source.id, DatasetImage.sha256 == digest)
    )
    if exists:
        return None
    width, height = 0, 0
    if kind == "image":
        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
        except OSError:
            return None
    filename = f"{digest[:24]}{suffix}"
    directory = _source_dir(source.id)
    try:
        (directory / filename).write_bytes(data)
    except OSError:
        return None
    thumb_name = None
    if kind == "video" and thumb is not None:
        thumb_data, thumb_suffix = thumb
        thumb_name = f"{digest[:24]}_thumb{thumb_suffix or '.jpg'}"
        try:
            (directory / thumb_name).write_bytes(thumb_data)
        except OSError:
            thumb_name = None
    item = DatasetImage(
        source_id=source.id,
        filename=filename,
        sha256=digest,
        kind=kind,
        thumb_filename=thumb_name,
        width=width,
        height=height,
        status="ready" if kind == "video" else "pending",
    )
    db.add(item)
    db.flush()
    return item


def store_image(db, source: DatasetSource, data: bytes, suffix: str) -> DatasetImage | None:
    return store_media(db, source, data, suffix, "image")


def media_counts(db, source_id: str) -> tuple[int, int]:
    rows = db.execute(
        select(DatasetImage.kind, func.count())
        .where(DatasetImage.source_id == source_id)
        .group_by(DatasetImage.kind)
    ).all()
    counts = {kind: count for kind, count in rows}
    return counts.get("image", 0), counts.get("video", 0)


def _import_url_list(source: DatasetSource, urls, limit: int, db) -> int:
    count = 0
    for raw in urls:
        if count >= limit:
            break
        url = raw.strip()
        if not url or url.startswith("#"):
            continue
        downloaded = download_image(url)
        if downloaded and store_image(db, source, downloaded[0], downloaded[1]):
            count += 1
    return count


def import_urls(source: DatasetSource, reference: str, limit: int, db) -> int:
    return _import_url_list(source, reference.splitlines(), limit, db)


# ------------------------------- X / Twitter -------------------------------

X_HANDLE = re.compile(r"^(?:(?:https?://)?(?:www\.)?(?:x|twitter)\.com/)?@?([A-Za-z0-9_]{1,15})(?:/.*)?(?:[?#].*)?$")
X_STATUS = re.compile(r"(?:x|twitter)\.com/[A-Za-z0-9_]{1,15}/status/(\d+)")
X_BEARER_DEFAULT = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
X_GRAPHQL_HOST = "https://x.com"
X_OPERATIONS = ("UserByScreenName", "UserTweets")
X_OPERATIONS_DOC = (
    "https://raw.githubusercontent.com/fa0311/TwitterInternalAPIDocument/master/docs/json/GraphQL.json"
)
X_MAX_PAGES = 8
X_OPERATIONS_TTL = 6 * 3600
_X_OPERATIONS_CACHE: dict = {"expires": 0.0, "data": {}}


def normalize_x_reference(reference: str) -> tuple[str, str | None]:
    """Accept @handle, profile URLs (also /media, /with_replies) and single post URLs."""
    text = reference.strip()
    status = X_STATUS.search(text)
    match = X_HANDLE.match(text)
    if not match:
        raise ValueError("Provide a public X profile (@name, https://x.com/name) or a post link")
    return match.group(1), (status.group(1) if status else None)


def normalize_x(reference: str) -> str:
    return normalize_x_reference(reference)[0]


def _parse_x_operations(js: str) -> dict:
    """Extract GraphQL query ids and feature flags for the requested operations from a web bundle."""
    operations: dict = {}
    for operation in X_OPERATIONS:
        marker = f'operationName:"{operation}"'
        index = js.find(marker)
        if index < 0:
            continue
        window = js[max(0, index - 600):index + 1500]
        candidates = list(re.finditer(r'queryId:"([A-Za-z0-9_-]+)"', window))
        if not candidates:
            continue
        offset = max(0, index - 600)
        query = min(candidates, key=lambda match: abs((offset + match.start()) - index))
        metadata = js[index:index + 1500]
        switches = re.search(r"featureSwitches:\[(.*?)\]", metadata, re.DOTALL)
        toggles = re.search(r"fieldToggles:\[(.*?)\]", metadata, re.DOTALL)
        operations[operation] = {
            "queryId": query.group(1),
            "features": {name: True for name in re.findall(r'"([^"]+)"', switches.group(1))} if switches else {},
            "fieldToggles": {name: True for name in re.findall(r'"([^"]+)"', toggles.group(1))} if toggles else {},
        }
    return operations


def _operations_from_document(document) -> dict:
    operations: dict = {}

    def walk(node):
        if isinstance(node, dict):
            name = node.get("operationName")
            if name in X_OPERATIONS and name not in operations and node.get("queryId"):
                meta = node.get("metadata") or {}
                operations[name] = {
                    "queryId": str(node["queryId"]),
                    "features": {switch: True for switch in meta.get("featureSwitches") or []},
                    "fieldToggles": {toggle: True for toggle in meta.get("fieldToggles") or []},
                }
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    return operations


def _x_media_urls(tweet: dict, urls: list, seen: set) -> None:
    legacy = tweet.get("legacy") or (tweet.get("tweet") or {}).get("legacy")
    if not legacy or legacy.get("retweeted_status_result"):
        return
    entities = legacy.get("extended_entities") or legacy.get("entities") or {}
    for media in entities.get("media") or []:
        if media.get("type") != "photo":
            continue
        raw = media.get("media_url_https")
        if not raw or raw in seen:
            continue
        seen.add(raw)
        urls.append(f"{raw}?name=large")


def x_timeline_photos(data: dict, limit: int) -> tuple[list[str], str | None]:
    """Photo URLs (largest size) plus the bottom cursor from a UserTweets timeline payload."""
    urls: list[str] = []
    seen: set = set()
    cursor = None
    user = data.get("data", {}).get("user", {}).get("result", {})
    container = user.get("timeline_v2") or user.get("timeline") or {}
    timeline = container.get("timeline") or container
    for instruction in timeline.get("instructions") or []:
        for entry in instruction.get("entries") or []:
            content = entry.get("content") or {}
            if str(entry.get("entryId", "")).startswith("cursor-") or content.get("cursorType") == "Bottom":
                cursor = content.get("value") or cursor
                continue
            results = []
            item = (content.get("itemContent") or {}).get("tweet_results", {}).get("result")
            if item:
                results.append(item)
            for module_item in content.get("items") or []:
                nested = ((module_item.get("item") or {}).get("itemContent") or {}).get("tweet_results", {}).get("result")
                if nested:
                    results.append(nested)
            for result in results:
                _x_media_urls(result, urls, seen)
        if len(urls) >= limit:
            break
    return urls[:limit], cursor


class XClient:
    """Anonymous guest-token client for public X profiles (no account, no cookies)."""

    def __init__(self):
        from curl_cffi import requests as curl_requests

        self.session = curl_requests.Session(impersonate="chrome")
        self.session.headers.update(
            {
                "accept-language": "en-US,en;q=0.9",
                "referer": "https://x.com/",
            }
        )
        self.bearer = (settings.x_bearer or "").strip() or X_BEARER_DEFAULT
        self.guest_token = ""
        self.operations: dict = {}
        self.warmed = False

    def _warm(self):
        if not self.warmed:
            self.session.get("https://x.com/", timeout=20)
            self.warmed = True

    def _activate(self):
        self._warm()
        response = self.session.post(
            "https://api.twitter.com/1.1/guest/activate.json",
            headers={"authorization": f"Bearer {self.bearer}"},
            timeout=20,
        )
        if response.status_code != 200:
            raise ValueError(f"X: could not obtain a guest token (HTTP {response.status_code})")
        self.guest_token = str(response.json().get("guest_token") or "")
        if not self.guest_token:
            raise ValueError("X: guest token not received")

    def _bootstrap(self):
        if _X_OPERATIONS_CACHE["data"] and _X_OPERATIONS_CACHE["expires"] > time.time():
            self.operations = _X_OPERATIONS_CACHE["data"]
            return
        self._warm()
        operations: dict = {}
        try:
            response = self.session.get(X_OPERATIONS_DOC, timeout=30)
            if response.status_code == 200:
                operations = _operations_from_document(response.json())
        except Exception as error:  # noqa: BLE001 - the document is optional; bundle scan is the fallback
            logger.info("X operations document failed: %s", error)
        if not all(name in operations for name in X_OPERATIONS):
            operations.update(
                {name: info for name, info in self._bundle_operations().items() if name not in operations}
            )
        if not all(name in operations for name in X_OPERATIONS):
            raise ValueError("X: GraphQL operations not found (X may have changed its structure)")
        _X_OPERATIONS_CACHE.update({"data": operations, "expires": time.time() + X_OPERATIONS_TTL})
        self.operations = operations

    def _bundle_operations(self) -> dict:
        """Fallback: scan the x.com scripts (and Vite chunks) for the operation metadata."""
        try:
            page = self.session.get("https://x.com/explore", timeout=30)
        except Exception as error:  # noqa: BLE001 - fallback only
            logger.info("X explore warmup failed: %s", error)
            return {}
        scripts = re.findall(r"https://abs\.twimg\.com/[^\"']+\.js", page.text)
        found: dict = {}
        chunks: list[str] = []
        for url in scripts[:12]:
            try:
                js = self.session.get(url, timeout=30).text
            except Exception as error:  # noqa: BLE001 - a missing chunk must not abort the bootstrap
                logger.info("X bundle chunk failed (%s): %s", url, error)
                continue
            found.update(_parse_x_operations(js))
            if all(name in found for name in X_OPERATIONS):
                return found
            base = url.rsplit("/", 1)[0] + "/assets/"
            chunks.extend(base + name for name in re.findall(r"\./assets/([A-Za-z0-9_\-\.]+\.js)", js))
        if not chunks:
            return found
        from concurrent.futures import ThreadPoolExecutor

        def scan(chunk_url: str) -> dict:
            try:
                from curl_cffi import requests as curl_requests

                session = curl_requests.Session(impersonate="chrome")
                return _parse_x_operations(session.get(chunk_url, timeout=20).text)
            except Exception:  # noqa: BLE001 - chunk scanning is best effort
                return {}

        with ThreadPoolExecutor(max_workers=10) as pool:
            for result in pool.map(scan, chunks[:150]):
                for name, info in result.items():
                    found.setdefault(name, info)
                if all(name in found for name in X_OPERATIONS):
                    break
        return found

    def _graphql(self, operation: str, variables: dict) -> dict:
        if not self.guest_token:
            self._activate()
        if not self.operations:
            self._bootstrap()
        for _ in range(4):
            info = self.operations[operation]
            url = f"{X_GRAPHQL_HOST}/i/api/graphql/{info['queryId']}/{operation}"
            response = self.session.get(
                url,
                params={
                    "variables": json.dumps(variables),
                    "features": json.dumps(info.get("features") or {}),
                    "fieldToggles": json.dumps(info.get("fieldToggles") or {}),
                },
                headers={
                    "authorization": f"Bearer {self.bearer}",
                    "x-guest-token": self.guest_token,
                    "x-twitter-active-user": "yes",
                    "x-twitter-client-language": "en",
                    "content-type": "application/json",
                    "origin": "https://x.com",
                },
                timeout=30,
            )
            if response.status_code in (401, 403):
                self._activate()
                continue
            if response.status_code == 404:
                if "Query not found" in response.text:
                    self.operations = {}
                    self._bootstrap()
                    continue
                raise ValueError("X: operation unavailable without login (auth wall)")
            if response.status_code == 429:
                raise ValueError("X rate-limited the requests (429): try again later")
            if response.status_code == 400:
                missing = re.search(r'features cannot be null:?\s*([^"}\n]+)', response.text)
                if missing:
                    for name in missing.group(1).replace(" and ", ",").split(","):
                        name = name.strip().strip(".")
                        if name:
                            info.setdefault("features", {})[name] = True
                    continue
                raise ValueError(f"X: request rejected (HTTP 400): {response.text[:200]}")
            if response.status_code != 200:
                raise ValueError(f"X: HTTP error {response.status_code}")
            return response.json()
        raise ValueError("X: request failed after retries")

    def _user_id(self, handle: str) -> str:
        data = self._graphql("UserByScreenName", {"screen_name": handle})
        result = ((data.get("data") or {}).get("user") or {}).get("result") or {}
        user_id = result.get("rest_id")
        if not user_id:
            raise ValueError(f"X: profile @{handle} not found or not accessible")
        return str(user_id)

    def tweet_photos(self, tweet_id: str, limit: int) -> list[str]:
        data = self._graphql("TweetResultByRestId", {"tweetId": tweet_id, "withCommunity": False, "includePromotedContent": False, "withVoice": False})
        result = ((data.get("data") or {}).get("tweetResult") or {}).get("result") or {}
        urls: list[str] = []
        seen: set = set()
        _x_media_urls(result, urls, seen)
        return urls[:limit]

    def profile_photos(self, handle: str, limit: int) -> list[str]:
        user_id = self._user_id(handle)
        photos: list[str] = []
        seen: set = set()
        cursor = None
        for _ in range(X_MAX_PAGES):
            variables = {
                "userId": user_id,
                "count": 40,
                "includePromotedContent": False,
                "withQuickPromoteEligibilityTweetFields": False,
                "withVoice": False,
                "withV2Timeline": True,
            }
            if cursor:
                variables["cursor"] = cursor
            batch, cursor = x_timeline_photos(self._graphql("UserTweets", variables), limit)
            for url in batch:
                if url not in seen:
                    seen.add(url)
                    photos.append(url)
            if len(photos) >= limit or not cursor:
                break
        return photos[:limit]


def fetch_x_images(reference: str, limit: int) -> list[str]:
    """Public X photo URLs (pose/style references, not likeness). No account involved."""
    handle, tweet_id = normalize_x_reference(reference)
    try:
        client = XClient()
        if tweet_id:
            photos = client.tweet_photos(tweet_id, limit)
            if not photos:
                raise ValueError("The linked post contains no photos")
            return photos
        photos = client.profile_photos(handle, limit)
        if not photos:
            raise ValueError(f"No recent photos found for @{handle} (maybe text only or a protected account)")
        return photos
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(f"X unreachable: {error}") from error


NEXTCLOUD_SHARE = re.compile(r"^https?://([^/]+)/s/([A-Za-z0-9]+)")


def parse_nextcloud_reference(reference: str) -> tuple[str, str, str]:
    """Return (base_url, token, folder) from a public Nextcloud share link."""
    match = NEXTCLOUD_SHARE.match(reference.strip())
    if not match:
        raise ValueError("Incolla un link pubblico Nextcloud (https://cloud.example.com/s/TOKEN), anche di una sottocartella")
    parsed = urlparse(reference.strip())
    folder = ""
    if parsed.query:
        params = parse_qs(parsed.query)
        folder = (params.get("path") or [""])[0]
    base = f"{parsed.scheme}://{parsed.netloc}/s/{match.group(2)}"
    return base, match.group(2), folder.strip("/")


NEXTCLOUD_DAV_ROOTS = ("/public.php/dav/files/{token}", "/public.php/webdav")


def _parse_nextcloud_propfind(xml: str, root_path: str, server: str = "") -> list[dict]:
    """Parse a WebDAV PROPFIND response; hrefs are paths relative to root_path."""
    from xml.etree import ElementTree

    def strip_namespace(tag: str) -> str:
        return tag.split("}", 1)[-1]

    entries: list[dict] = []
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return entries
    for response in root.iter():
        if strip_namespace(response.tag) != "response":
            continue
        href = ""
        length = 0
        is_dir = False
        for element in response.iter():
            name = strip_namespace(element.tag)
            if name == "href" and element.text:
                href = element.text
            elif name == "getcontentlength" and element.text:
                try:
                    length = int(element.text)
                except ValueError:
                    length = 0
            elif name == "collection":
                is_dir = True
        if not href:
            continue
        marker = root_path.rstrip("/") + "/"
        index = href.find(marker)
        if index < 0:
            continue
        relative = href[index + len(marker):]
        if not relative:
            continue
        suffix = Path(relative.rstrip("/")).suffix.lower()
        entries.append(
            {
                "path": unquote(relative).rstrip("/"),
                "url": f"{server}{root_path.rstrip('/')}/{relative}",
                "is_dir": is_dir or href.endswith("/"),
                "size": length,
                "suffix": suffix,
            }
        )
    return entries


def import_nextcloud(source: DatasetSource, reference: str, limit: int, db) -> int:
    """Import images from a public Nextcloud share (link to the share or a subfolder)."""
    base, token, folder = parse_nextcloud_reference(reference)
    server = base[: base.index("/s/")]
    count = 0
    visited = 0
    queue = [folder]
    root_path: str | None = None
    with httpx.Client(auth=(token, ""), timeout=60, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
        while queue and count < limit and visited < 200:
            current = queue.pop(0)
            visited += 1
            relative = current.strip("/") + ("/" if current else "")
            response = None
            candidates = [root_path] if root_path else [template.format(token=token) for template in NEXTCLOUD_DAV_ROOTS]
            for candidate in candidates:
                try:
                    probe = client.request("PROPFIND", f"{server}{candidate}/{quote(relative)}", headers={"Depth": "1"})
                except httpx.HTTPError:
                    continue
                if probe.status_code in (200, 207):
                    root_path = candidate
                    response = probe
                    break
            if response is None or root_path is None:
                if current == folder:
                    raise ValueError(
                        "Nextcloud share unreachable: the server must allow public WebDAV (PROPFIND)"
                    )
                continue
            for entry in _parse_nextcloud_propfind(response.text, root_path, server):
                if entry["is_dir"]:
                    if visited + len(queue) < 200:
                        queue.append(entry["path"])
                elif entry["suffix"] in IMAGE_EXTENSIONS and count < limit:
                    try:
                        download = client.get(entry["url"])
                        download.raise_for_status()
                    except httpx.HTTPError:
                        continue
                    if store_image(db, source, download.content, entry["suffix"]):
                        count += 1
    return count


def import_x(source: DatasetSource, reference: str, limit: int, db) -> int:
    urls = fetch_x_images(reference, limit)
    return _import_url_list(source, urls, limit, db)


def import_folder(source: DatasetSource, reference: str, limit: int, db) -> int:
    root = Path(reference).expanduser()
    if not root.is_absolute():
        root = settings.dataset_import_dir / reference
    root = root.resolve()
    if not root.is_relative_to(settings.dataset_import_dir.resolve()) or not root.is_dir():
        raise ValueError("Invalid folder: use a path inside data/imports")
    count = 0
    for path in sorted(root.rglob("*")):
        if count >= limit:
            break
        suffix = path.suffix.lower()
        if not path.is_file() or suffix not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        kind = "video" if suffix in VIDEO_EXTENSIONS else "image"
        if kind == "video" and len(data) > settings.dataset_video_max_bytes:
            continue
        if store_media(db, source, data, suffix, kind):
            count += 1
    return count


def import_telegram(source: DatasetSource, reference: str, limit: int, db) -> int:
    channel = reference.strip().rstrip("/")
    for prefix in ("https://t.me/s/", "https://t.me/", "http://t.me/s/", "http://t.me/", "t.me/s/", "t.me/"):
        channel = channel.removeprefix(prefix)
    channel = channel.lstrip("@")
    if not channel:
        raise ValueError("Invalid Telegram channel")
    seen_images: set[str] = set()
    seen_videos: set[str] = set()
    order_images: list[str] = []
    order_videos: list[tuple[str, str]] = []
    before: int | None = None
    empty_pages = 0
    pages = 0
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        while len(order_images) + len(order_videos) < limit and empty_pages < 4 and pages < 300:
            pages += 1
            params = {"before": before} if before else None
            try:
                response = client.get(f"https://t.me/s/{channel}", params=params)
                response.raise_for_status()
            except httpx.HTTPError as error:
                raise ValueError(f"Telegram channel unreachable: {error}") from error
            page = parse_telegram_page(response.text)
            new_items = 0
            for url in page["images"]:
                key = url.split("?")[0]
                if key not in seen_images:
                    seen_images.add(key)
                    order_images.append(url)
                    new_items += 1
            for entry in page["videos"]:
                key = entry["url"].split("?")[0]
                if key not in seen_videos:
                    seen_videos.add(key)
                    order_videos.append((entry["url"], entry["thumb"]))
                    new_items += 1
            empty_pages = empty_pages + 1 if new_items == 0 else 0
            next_before = page["before"]
            if next_before is None or (before is not None and next_before >= before):
                break
            before = next_before
            time.sleep(0.4)
    count = 0
    for url in order_images:
        if count >= limit:
            break
        downloaded = download_media(url, "image")
        if downloaded and store_media(db, source, downloaded[0], downloaded[1], "image"):
            count += 1
    for url, thumb_url in order_videos:
        if count >= limit:
            break
        downloaded = download_media(url, "video")
        if downloaded is None:
            continue
        thumb = download_media(thumb_url, "image")
        if store_media(db, source, downloaded[0], downloaded[1], "video", thumb=thumb):
            count += 1
    return count


def run_import(source_id: str, reference: str, limit: int, classify: bool) -> None:
    """Background task: import, then optionally describe every imported image."""
    try:
        with Session.begin() as db:
            source = db.get(DatasetSource, source_id)
            if source is None:
                return
            source.status = "importing"
            source.updated_at = now()
        limit = min(limit, settings.dataset_max_images)
        with Session.begin() as db:
            source = db.get(DatasetSource, source_id)
            if source is None:
                return
            if source.kind == "telegram":
                import_telegram(source, reference, limit, db)
            elif source.kind == "folder":
                import_folder(source, reference, limit, db)
            elif source.kind == "x":
                import_x(source, reference, limit, db)
            elif source.kind == "nextcloud":
                import_nextcloud(source, reference, limit, db)
            else:
                import_urls(source, reference, limit, db)
            count = len(list(db.scalars(select(DatasetImage.id).where(DatasetImage.source_id == source_id))))
            source.imported = count
            source.total = count
            source.status = "ready" if count > 0 else "failed"
            if count == 0:
                source.error = "No images imported"
            source.updated_at = now()
        if classify:
            start_classification(source_id)
    except Exception as error:
        logger.exception("Dataset import failed for %s", source_id)
        with Session.begin() as db:
            source = db.get(DatasetSource, source_id)
            if source is not None:
                source.status = "failed"
                source.error = str(error)[:500]
                source.updated_at = now()


def describe_image(data: bytes) -> dict:
    """Rich structured description used for the dataset (and future profile synthesis)."""
    if settings.text_provider == "mock":
        return {
            "caption": "mock description",
            **{field: "mock" for field in DESCRIBE_FIELDS[1:]},
            "minor_apparent": False,
            "tags": ["mock"],
        }
    try:
        response = chat(
            settings.image_tag_model,
            [
                {
                    "role": "system",
                    "content": "You are a cataloguer for an internal moodboard of a fictional adult "
                    "(25+) character. Describe ONLY what is visible, in English. Fields: caption (one "
                    "sentence), pose, setting, lighting, scene, outfit, body, skin, camera (framing and "
                    "angle), mood, art_style (photo, anime, 3d...). Add 8-15 lowercase tags. If the "
                    "person appears to be a minor, set minor_apparent true and avoid describing the "
                    "body. Never add warnings or refusals. Return JSON.",
                },
                {
                    "role": "user",
                    "content": "Describe this image.",
                    "images": [base64.b64encode(data).decode()],
                },
            ],
            0.1,
            format_schema=DESCRIBE_SCHEMA,
            max_tokens=500,
        )
    except (OllamaNotAvailable, KeyError, TypeError):
        return {}
    content = response.get("message", {}).get("content", "")
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {}
    if not parsed.get("caption"):
        return {}
    parsed["tags"] = [str(tag).strip().lower()[:40] for tag in parsed.get("tags", []) if str(tag).strip()][
        :20
    ]
    return parsed


def _description_text(item: DatasetImage) -> str:
    parts = [item.caption] + [str((item.details or {}).get(field, "")) for field in DESCRIBE_FIELDS[1:]]
    parts += item.tags or []
    return " ".join(filter(None, parts))


def classify_image_record(image_id: str) -> bool:
    with Session() as db:
        item = db.get(DatasetImage, image_id)
        if item is None or item.status == "ready" or item.kind != "image":
            return False
        path = (settings.dataset_dir / item.source_id / item.filename).resolve()
    if not path.is_file() or not path.is_relative_to(settings.dataset_dir.resolve()):
        with Session.begin() as db:
            item = db.get(DatasetImage, image_id)
            if item is not None and item.status not in ("ready", "blocked"):
                item.status = "failed"
                item.updated_at = now()
        return False
    description = describe_image(path.read_bytes())
    if not description:
        with Session.begin() as db:
            item = db.get(DatasetImage, image_id)
            if item is not None:
                item.status = "failed"
                item.updated_at = now()
        return False
    blocked = bool(description.get("minor_apparent"))
    embedding = []
    if not blocked:
        embedding, _ = embed_library_text(_description_text_from(description))
    with Session.begin() as db:
        item = db.get(DatasetImage, image_id)
        if item is None:
            return False
        item.caption = description.get("caption", "")
        item.details = {field: description.get(field, "") for field in DESCRIBE_FIELDS[1:]}
        item.tags = description.get("tags", [])
        item.embedding = embedding
        item.status = "blocked" if blocked else "ready"
        item.updated_at = now()
    return True


def _description_text_from(description: dict) -> str:
    parts = [description.get("caption", "")]
    parts += [str(description.get(field, "")) for field in DESCRIBE_FIELDS[1:]]
    parts += description.get("tags", [])
    return " ".join(filter(None, parts))


def classification_counts(db, source_id: str) -> dict:
    rows = db.execute(
        select(DatasetImage.status, func.count())
        .where(DatasetImage.source_id == source_id, DatasetImage.kind == "image")
        .group_by(DatasetImage.status)
    ).all()
    counts = {status: count for status, count in rows}
    ready = counts.get("ready", 0)
    blocked = counts.get("blocked", 0)
    failed = counts.get("failed", 0)
    pending = counts.get("pending", 0)
    return {
        "ready": ready,
        "blocked": blocked,
        "failed": failed,
        "pending": pending,
        "classified": ready + blocked + failed,
        "total": ready + blocked + failed + pending,
    }


def active_classification_job(db, source_id: str) -> ExecutionJob | None:
    return db.scalar(
        select(ExecutionJob).where(
            ExecutionJob.type == "dataset_classify",
            ExecutionJob.external_id == source_id,
            ExecutionJob.state.in_(("queued", "running")),
        )
    )


def enqueue_classification(source_id: str) -> dict:
    """Create one idempotent classification job; duplicate requests reuse the active job."""
    with Session.begin() as db:
        source = db.get(DatasetSource, source_id)
        if source is None:
            return {"started": False, "state": "missing"}
        active = active_classification_job(db, source_id)
        if active is not None:
            return {"started": False, "job_id": active.id, "state": active.state}
        job = create_job(
            db,
            type="dataset_classify",
            external_id=source_id,
            message=f"classify source {source.name}",
        )
        source.status = "classifying"
        source.error = None
        source.updated_at = now()
        return {"started": True, "job_id": job.id, "state": "queued"}


def start_classification(source_id: str, *, worker: str = "api") -> dict:
    """Enqueue and run a classification job inline (used by imports)."""
    result = enqueue_classification(source_id)
    if result.get("started") and result.get("job_id"):
        classify_source_job(source_id, result["job_id"], worker=worker)
        with Session() as db:
            job = db.get(ExecutionJob, result["job_id"])
            result["state"] = job.state if job else "unknown"
    return result


def classify_source_job(source_id: str, job_id: str, *, worker: str = "api") -> None:
    """Describe every image without a terminal description, tracked as an execution job."""
    with Session.begin() as db:
        job = db.get(ExecutionJob, job_id)
        if job is None or job.state not in ("queued", "running"):
            return
        if job.state == "queued":
            start_job(db, job, worker=worker)
        update_progress(db, job, unit="images")
        ids = list(
            db.scalars(
                select(DatasetImage.id).where(
                    DatasetImage.source_id == source_id,
                    DatasetImage.status.in_(["pending", "failed"]),
                    DatasetImage.kind == "image",
                )
            )
        )
        counts = classification_counts(db, source_id)
        update_progress(db, job, current=counts["classified"], total=counts["total"])
    try:
        for image_id in ids:
            with Session() as db:
                job = db.get(ExecutionJob, job_id)
                if job is not None and job.cancel_requested:
                    with Session.begin() as db2:
                        finish_job(db2, db2.get(ExecutionJob, job_id), state="canceled")
                    break
            classify_image_record(image_id)
            with Session.begin() as db:
                job = db.get(ExecutionJob, job_id)
                source = db.get(DatasetSource, source_id)
                counts = classification_counts(db, source_id)
                if job is not None:
                    update_progress(db, job, current=counts["classified"], total=counts["total"])
                if source is not None:
                    source.classified = counts["classified"]
                    source.updated_at = now()
        with Session.begin() as db:
            job = db.get(ExecutionJob, job_id)
            source = db.get(DatasetSource, source_id)
            counts = classification_counts(db, source_id)
            if source is not None:
                source.classified = counts["classified"]
                source.updated_at = now()
                if counts["total"] == 0 or (counts["pending"] == 0 and counts["failed"] == 0):
                    source.status = "ready"
                elif counts["ready"] + counts["blocked"] > 0:
                    source.status = "partial"
                    source.error = f"{counts['failed']} images could not be described"
                else:
                    source.status = "failed"
                    source.error = "No image could be described"
            if job is not None and job.state == "running":
                summary = f"{counts['ready']} ready, {counts['blocked']} blocked, {counts['failed']} failed"
                if counts["ready"] + counts["blocked"] == 0 and counts["failed"] > 0:
                    finish_job(
                        db,
                        job,
                        state="failed",
                        error_info={
                            "code": "classification_failed",
                            "summary": "No image could be described.",
                            "remediation": "Check the vision model and the source files, then retry.",
                            "technical_details": summary,
                        },
                    )
                else:
                    finish_job(db, job, state="succeeded", message=summary)
    except Exception as error:
        logger.exception("Dataset classification failed for %s", source_id)
        with Session.begin() as db:
            job = db.get(ExecutionJob, job_id)
            source = db.get(DatasetSource, source_id)
            if source is not None:
                source.status = "failed"
                source.error = str(error)[:500]
                source.updated_at = now()
            if job is not None and job.state in ("queued", "running"):
                finish_job(
                    db,
                    job,
                    state="failed",
                    error_info={
                        "code": "classification_failed",
                        "summary": "Dataset classification failed.",
                        "remediation": "Retry the classification; if it keeps failing check the vision model.",
                        "technical_details": str(error)[:800],
                    },
                )


def reconcile_classifying_sources(db) -> int:
    """Sources stuck in ``classifying`` with no healthy job become resumable again.

    Stale classification jobs (dead heartbeat, e.g. after an API restart) are failed
    with the standard stale handling before the source is reconciled.
    """
    from .jobs import finish_job, is_stale

    active: set[str] = set()
    for job in db.scalars(
        select(ExecutionJob).where(
            ExecutionJob.type == "dataset_classify",
            ExecutionJob.state.in_(("queued", "running")),
            ExecutionJob.external_id.is_not(None),
        )
    ):
        if is_stale(job):
            finish_job(
                db,
                job,
                state="failed",
                error_info={
                    "code": "stale_heartbeat",
                    "summary": "The job stopped sending heartbeats and was marked failed.",
                    "remediation": "Resume the classification; if it keeps stalling check the API worker.",
                    "technical_details": f"last heartbeat: {job.heartbeat_at}",
                },
                message="recovered: stale heartbeat",
            )
        else:
            active.add(job.external_id)
    sources = db.scalars(select(DatasetSource).where(DatasetSource.status == "classifying")).all()
    reconciled = 0
    for source in sources:
        if source.id in active:
            continue
        counts = classification_counts(db, source.id)
        source.status = "stalled" if counts["pending"] or counts["failed"] else "ready"
        source.updated_at = now()
        reconciled += 1
    return reconciled


def source_out(source: DatasetSource, images: int | None = None, videos: int = 0, counts: dict | None = None) -> dict:
    counts = counts or {}
    return {
        "id": source.id,
        "name": source.name,
        "kind": source.kind,
        "reference": source.reference,
        "character_id": source.character_id,
        "status": source.status,
        "total": source.total,
        "imported": source.imported,
        "classified": source.classified,
        "ready": counts.get("ready", 0),
        "pending": counts.get("pending", 0),
        "failed": counts.get("failed", 0),
        "blocked": counts.get("blocked", 0),
        "skipped": max(0, (source.imported or 0) - counts.get("total", 0)),
        "images": images if images is not None else (source.imported or 0),
        "videos": videos,
        "error": source.error,
        "created_at": source.created_at.isoformat(),
        "updated_at": source.updated_at.isoformat() if source.updated_at else None,
    }


def image_out(item: DatasetImage) -> dict:
    return {
        "id": item.id,
        "source_id": item.source_id,
        "filename": item.filename,
        "kind": item.kind,
        "has_thumb": bool(item.thumb_filename),
        "width": item.width,
        "height": item.height,
        "status": item.status,
        "caption": item.caption,
        "details": item.details or {},
        "tags": item.tags or [],
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def export_rows(source_id: str) -> list[dict]:
    with Session() as db:
        items = list(
            db.scalars(
                select(DatasetImage)
                .where(DatasetImage.source_id == source_id, DatasetImage.status == "ready")
                .order_by(DatasetImage.created_at)
            )
        )
    return [
        {
            "id": item.id,
            "kind": item.kind,
            "caption": item.caption,
            **{field: (item.details or {}).get(field, "") for field in DESCRIBE_FIELDS[1:]},
            "tags": item.tags or [],
            "width": item.width,
            "height": item.height,
        }
        for item in items
    ]


def synthesize_profile(source_id: str) -> dict:
    """Draft a character profile from the dataset descriptions of a source."""
    rows = export_rows(source_id)
    if not rows:
        raise ValueError("The source has no classified images")
    if settings.text_provider == "mock":
        return CharacterProfile(
            description="mock dataset profile",
            appearance="mock appearance",
            likes="mock interests",
        ).model_dump()
    sample = rows[:60]
    schema = {
        "type": "object",
        "properties": {name: {"type": "string"} for name in CharacterProfile.model_fields},
        "required": list(CharacterProfile.model_fields),
        "additionalProperties": False,
    }
    try:
        response = chat(
            settings.image_prompt_model,
            [
                {
                    "role": "system",
                    "content": "You design a fictional adult (25+) AI influencer from a moodboard dataset. "
                    "Read the image descriptions and synthesize a coherent character: identity, physical "
                    "appearance, style, interests and tone. Never copy a real person, keep it generic and "
                    "original. Adult only. Output JSON matching the schema, one or two sentences per field, "
                    "language code (it/en) in the language field. This is a draft for human review.",
                },
                {"role": "user", "content": json.dumps(sample, ensure_ascii=False)[:12000]},
            ],
            0.6,
            format_schema=schema,
            max_tokens=2048,
        )
    except (OllamaNotAvailable, KeyError, TypeError) as error:
        raise ValueError(f"Synthesis failed: {error}") from error
    content = response.get("message", {}).get("content", "")
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    try:
        return CharacterProfile.model_validate_json(content).model_dump()
    except (ValueError, TypeError) as error:
        raise ValueError("The model did not return a valid profile") from error


def delete_source_files(source_id: str) -> None:
    directory = (settings.dataset_dir / source_id).resolve()
    if not directory.is_relative_to(settings.dataset_dir.resolve()) or not directory.is_dir():
        return
    for path in directory.iterdir():
        if path.is_file():
            path.unlink(missing_ok=True)
    directory.rmdir()


def delete_source(source_id: str) -> None:
    with Session.begin() as db:
        db.execute(delete(DatasetImage).where(DatasetImage.source_id == source_id))
        db.execute(delete(DatasetSource).where(DatasetSource.id == source_id))
    delete_source_files(source_id)
