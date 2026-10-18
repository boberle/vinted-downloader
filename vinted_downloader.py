from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from html import unescape
from html.parser import HTMLParser
from abc import abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast, Protocol, Generator
from urllib.parse import urlparse

import requests

AUTHOR_EMAIL = "contact@boberle.com"
ERROR_FILE = "vinted_product_downloader_error.txt"
SNAP = [1, 2, 3]


class ItemUnavailableError(RuntimeError):
    """The requested listing is unavailable in this response."""


class _NotFoundPageParser(HTMLParser):
    """Recognize Vinted's rendered error page, not JS route references."""

    found = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if ("data-testid", "page-not-found") in attrs:
            self.found = True


def is_not_found_page(html_content: str) -> bool:
    parser = _NotFoundPageParser()
    parser.feed(html_content)
    parser.close()
    return parser.found


@dataclass
class Summary:
    source: str
    title: str
    seller: str
    seller_id: int

    def __str__(self) -> str:
        summary = f"source: {self.source}\n"
        summary += f"title: {self.title}\n"
        summary += f"seller: {self.seller}\n"
        summary += f"seller id: {self.seller_id}\n"
        return summary


@dataclass
class Downloader:
    client_factory: ClientFactory
    writer: Writer

    def download(
        self,
        item_url: str,
        download_seller_profile: bool,
        download_all_seller_items: bool,
    ) -> None:
        vinted_tld = self._get_vinted_tld(item_url)
        client = self.client_factory.build(vinted_tld=vinted_tld)
        details = Details(client.download_item_details(item_url=item_url))

        if download_all_seller_items:
            data = client.download_items_details(details.seller_id)

            for item in data["items"]:
                item_id = item["id"]
                item_dir = Path(str(item_id))
                summary = Summary(
                    source=item["url"],
                    title=item["title"],
                    seller=item["user"]["login"],
                    seller_id=item["user"]["id"]
                )

                # Write item data to the item's subfolder
                self.writer.write_text(
                    item_dir / "item.json", json.dumps(item)
                )
                self.writer.write_text(
                    item_dir / "item_summary", str(summary)
                )

                # Extract photo URLs directly from the API response
                photo_urls = [
                    get_photo_url(photo) for photo in item.get("photos", [])
                ]

                # Get extension from URL
                photo_url = photo_urls[0]
                extension = Path(urlparse(photo_url).path).suffix

                for i, photo_bytes in enumerate(
                    client.download_photos(*photo_urls)
                ):
                    self.writer.write_bytes(
                        item_dir / f"photo_{i:02d}{extension}", photo_bytes
                    )
        else:
            summary = Summary(
                source=item_url,
                title=details.title,
                seller=details.seller,
                seller_id=details.seller_id
            )

            self.writer.write_text(Path("item.json"), json.dumps(details.data))
            self.writer.write_text(Path("item_summary"), str(summary))

            photo_urls = details.full_size_photo_urls
            for i, photo_bytes in enumerate(
                client.download_photos(*photo_urls)
            ):
                extension = (
                    Path(urlparse(photo_urls[i]).path).suffix or ".webp"
                )
                self.writer.write_bytes(
                    Path(f"photo_{i:02d}{extension}"), photo_bytes
                )

        if download_seller_profile and details.seller_photo_url:
            photo_bytes = client.download_photo(details.seller_photo_url)
            self.writer.write_bytes(Path("seller.webp"), photo_bytes)

    @staticmethod
    def _get_vinted_tld(item_url: str) -> str:
        match = re.search(r"(?<=vinted\.)[a-z.]+(?=/)", item_url)
        if match is None:
            raise RuntimeError("Unable to find vinted tld")
        vinted_tld = match.group(0)
        return vinted_tld

    @staticmethod
    def _save_json(path: Path, data: dict[str, Any]) -> None:
        json.dump(data, path.open("w", encoding="utf-8"), indent=2)


class Client(Protocol):
    @abstractmethod
    def download_item_details(self, item_url: str) -> dict[str, Any]:
        ...

    @abstractmethod
    def download_items_details(self, profile_id: int) -> dict[str, Any]:
        ...

    @abstractmethod
    def download_photos(self, *urls: str) -> Generator[bytes, None, None]:
        ...

    @abstractmethod
    def download_photo(self, url: str) -> bytes:
        ...


@dataclass
class VintedClient(Client):
    vinted_tld: str
    nap: list[int] | None = field(default_factory=lambda: SNAP)

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/155.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        })
        # Connect the first time to get the anonymous cookie auth
        self.session.get(f"https://www.vinted.{self.vinted_tld}") 

    def download_item_details(self, item_url: str) -> dict[str, Any]:
        self._nap()
        print("downloading details from '%s'" % item_url)
        response = self.session.get(item_url)
        if response.status_code in (404, 410):
            raise ItemUnavailableError(
                f"Item unavailable: Vinted returned HTTP {response.status_code} "
                f"for {item_url}."
            )
        response.raise_for_status()
        response_text = response.text
        # Some error pages are served with HTTP 200. Detect the rendered
        # marker rather than generic Next.js notFound strings, which can
        # also be embedded in valid listing pages.
        if is_not_found_page(response_text):
            raise ItemUnavailableError(
                "Item unavailable: Vinted returned its 'Page not found' page "
                f"for {item_url}."
            )
        try:
            data = extract_details_from_html_with_dto(response_text)
            if data is not None:
                print("Found data with the 'itemDto' method")
                return data
            data = extract_details_from_html_with_full_size_url(
                response_text
            )
            if data is not None:
                print("Found data with the 'full_size_url' method")
                return data
            # Current Vinted pages no longer embed the item JSON at all:
            # the page is rendered server-side and only carries resized
            # (800px) photos, JSON-LD metadata and the seller's profile
            # link. Build the item data from those, then try to upgrade
            # the photos to full size through the seller's wardrobe API
            # (the endpoint already used by --all-items).
            try:
                item_id: int | None = get_item_id(item_url)
            except RuntimeError:
                item_id = None
            data = extract_details_from_html_page(response_text, item_id)
            if data is None:
                Path(ERROR_FILE).write_bytes(response.content)
                raise ValueError(
                    "Unable to extract product details from the HTML. "
                    f"The server response has been saved in {ERROR_FILE}."
                )
            print(
                "Found data with the 'page' method (%d photos)"
                % len(data.get("photos", []))
            )
            if item_id is not None:
                data["id"] = item_id
            user = data.get("user")
            seller_id = user.get("id") if isinstance(user, dict) else None
            if item_id and seller_id:
                full = self._find_item_in_wardrobe(seller_id, item_id)
                if full is None and data.get("can_buy") is False:
                    print(
                        "This item is no longer for sale (sold, reserved or "
                        "closed): sellers' wardrobes only list active items, "
                        "so its full-size photos can't be fetched"
                    )
                if full is not None:
                    for key, value in data.items():
                        full.setdefault(key, value)
                    # some listings carry a single "photo" (the cover)
                    # instead of the "photos" list: graft its full-size
                    # URL onto the matching page photo
                    cover = full.get("photo")
                    if isinstance(cover, dict) and cover.get("full_size_url"):
                        for photo in full.get("photos", []):
                            if isinstance(photo, dict) and (
                                photo.get("url") == cover.get("url")
                                or photo.get("id") == cover.get("id")
                            ):
                                photo.setdefault(
                                    "full_size_url", cover["full_size_url"]
                                )
                    n_full = sum(
                        1 for p in full.get("photos", [])
                        if isinstance(p, dict) and p.get("full_size_url")
                    )
                    if n_full:
                        print(
                            "Upgraded: %d of %d photos have full-size URLs "
                            "from the wardrobe"
                            % (n_full, len(full.get("photos", [])))
                        )
                        return full
                    print(
                        "Wardrobe item found, but it carries no full-size "
                        "URLs either"
                    )
                    data = full
            dims = sorted(
                {
                    (int(p["width"]), int(p["height"]))
                    for p in data.get("photos", [])
                    if isinstance(p, dict)
                    and p.get("width") and p.get("height")
                }
            )
            size_note = (
                " (the originals are %s)"
                % ", ".join("%dx%d" % d for d in dims)
                if dims else ""
            )
            print(
                "Note: Vinted only serves the 800px rendition of the "
                "photos to the web%s, downloading those" % size_note
            )
            return data
        except json.JSONDecodeError:
            open(
                "vinted_product_downloader_error.txt", "wb"
            ).write(response.content)
            print(
                "=========\n"
                "An error occurred while decoding the product details.\n"
                "The content of the response has been saved in "
                f"{ERROR_FILE}.\n"
                "You can review the file, or send it to the developers at "
                f"{AUTHOR_EMAIL}\n"
                "for further assistance.\n"
                "========="
            )
            sys.exit(1)

    def _find_item_in_wardrobe(
        self, seller_id: int, item_id: int, max_pages: int = 10
    ) -> dict[str, Any] | None:
        url = (
            f"https://www.vinted.{self.vinted_tld}"
            f"/api/v2/wardrobe/{seller_id}/items"
        )
        headers = {
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": (
                f"https://www.vinted.{self.vinted_tld}/member/{seller_id}"
            ),
        }
        seen_first_ids: set[str] = set()
        seen_items = 0
        try:
            page = 1
            while page <= max_pages:
                if page > 1:
                    self._nap()
                params: dict[str, Any] = {
                    "page": page,
                    "per_page": 96,
                    "order": "relevance",
                }
                response = self.session.get(
                    url, headers=headers, params=params
                )
                if response.status_code != 200:
                    print(
                        "wardrobe request failed with status %d"
                        % response.status_code
                    )
                    return None
                try:
                    data = response.json()
                except ValueError:
                    print(
                        "wardrobe response is not JSON (content-type: %s)"
                        % response.headers.get("Content-Type", "?")
                    )
                    return None
                if not isinstance(data, dict):
                    print("wardrobe response has an unexpected shape")
                    return None
                items = data.get("items") or []
                pagination = data.get("pagination") or {}
                print(
                    "wardrobe page %d: %d items, pagination=%s, "
                    "full_size_url present: %s"
                    % (
                        page,
                        len(items),
                        json.dumps(pagination, separators=(",", ":"))[:160],
                        "full_size_url" in response.text,
                    )
                )
                for entry in items:
                    if not isinstance(entry, dict):
                        continue
                    candidate = entry
                    if isinstance(entry.get("item"), dict):
                        candidate = entry["item"]
                    candidate_id = candidate.get("id", candidate.get("item_id"))
                    if str(candidate_id) == str(item_id):
                        return cast(dict[str, Any], candidate)
                seen_items += len(items)
                if not items:
                    print(
                        "wardrobe returned no items (keys: %s)"
                        % ", ".join(sorted(data.keys()))[:120]
                    )
                    return None
                # guard against an endpoint that ignores the page parameter
                first = items[0] if isinstance(items[0], dict) else {}
                first_id = str(first.get("id", first.get("item_id")))
                if first_id in seen_first_ids:
                    print("wardrobe pagination repeats, stopping")
                    return None
                seen_first_ids.add(first_id)
                total_pages = pagination.get("total_pages")
                if total_pages is None:
                    total_entries = pagination.get("total_entries")
                    per_page = pagination.get("per_page") or len(items)
                    if total_entries and per_page:
                        total_pages = -(-int(total_entries) // int(per_page))
                if total_pages is not None and page >= int(total_pages):
                    print(
                        "item not found among the seller's %d wardrobe items"
                        % seen_items
                    )
                    return None
                page += 1
        except requests.RequestException as exc:
            print("wardrobe request failed: %s" % exc)
            return None
        print(
            "item not found in the first %d wardrobe pages (%d items)"
            % (max_pages, seen_items)
        )
        return None

    def download_items_details(self, profile_id: int) -> dict[str, Any]:
        self._nap()
        self.session.get(
            f"https://www.vinted.{self.vinted_tld}/member/{profile_id}"
        )
        url = (
            f"https://www.vinted.{self.vinted_tld}/api/v2/wardrobe/{profile_id}/items"
        )
        headers = {
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://www.vinted.{self.vinted_tld}/member/{profile_id}",
        }
        data: dict[str, Any] = {}
        all_items: list[Any] = []
        page = 1
        while True:
            if page > 1:
                self._nap()
            params: dict[str, Any] = {
                "page": page,
                "per_page": 96,
                "order": "relevance",
            }
            response = self.session.get(url, headers=headers, params=params)
            data = cast(dict[str, Any], response.json())
            items = data.get("items", [])
            all_items.extend(items)
            pagination = data.get("pagination") or {}
            total_pages = pagination.get("total_pages")
            current_page = pagination.get("current_page", page)
            if not items:
                break
            if total_pages is None or current_page >= total_pages:
                break
            page += 1
        data["items"] = all_items
        return data

    def _nap(self) -> None:
        if self.nap is not None and len(self.nap):
            time.sleep(random.choice(self.nap))

    def download_photos(self, *urls: str) -> Generator[bytes, None, None]:
        for url in urls:
            yield self.download_photo(url)

    def download_photo(self, url: str) -> bytes:
        return self._download_resource(url)

    def _download_resource(self, url: str) -> bytes:
        self._nap()
        print("downloading resource from '%s'" % url)
        resource = self.session.get(url).content
        return resource


class ClientFactory(Protocol):
    @abstractmethod
    def build(self, vinted_tld: str) -> Client:
        ...


class VintedClientFactory(ClientFactory):
    def build(self, vinted_tld: str) -> VintedClient:
        return VintedClient(vinted_tld=vinted_tld)


class Writer(Protocol):
    @abstractmethod
    def write_text(self, file: Path, data: str) -> None:
        ...

    @abstractmethod
    def write_bytes(self, file: Path, data: bytes) -> None:
        ...


@dataclass
class FileWriter(Writer):
    output_dir: Path

    def write_text(self, file: Path, data: str) -> None:
        self._create()
        full_path = self.output_dir / file
        # Create parent directories if they don't exist
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(data, encoding="utf-8")

    def write_bytes(self, file: Path, data: bytes) -> None:
        self._create()
        full_path = self.output_dir / file
        # Create parent directories if they don't exist
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)

    def _create(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)


def get_photo_url(photo: dict[str, Any]) -> str:
    # Older payloads: full_size_url.
    # Newer Next.js payloads only expose url (the largest available size).
    return str(photo.get("full_size_url") or photo["url"])


@dataclass
class Details:
    data: dict[str, Any]

    @property
    def title(self) -> str:
        return str(self.data.get("title", ""))

    @property
    def seller(self) -> str:
        # Older payloads: user.login or top-level login.
        # Newer Next.js payloads don't include the seller name at all.
        user = self.data.get("user")
        if isinstance(user, dict) and "login" in user:
            return str(user["login"])
        return str(self.data.get("login", ""))

    @property
    def seller_id(self) -> int:
        # Older payloads: user.id or seller_id.
        # Newer Next.js payloads only expose ownerId.
        user = self.data.get("user")
        if isinstance(user, dict) and "id" in user:
            return cast(int, user["id"])
        for key in ("seller_id", "ownerId"):
            if key in self.data:
                return cast(int, self.data[key])
        return 0

    @property
    def full_size_photo_urls(self) -> list[str]:
        return [get_photo_url(photo) for photo in self.data["photos"]]

    @property
    def seller_photo_url(self) -> str | None:
        try:
            url = self.data["user"]["photo"]["full_size_url"]
        except (KeyError, TypeError):
            return None
        else:
            return url or None


def main() -> int:
    args = parse_args()
    item_url: str = args.item_url
    download_seller_profile: bool = args.seller
    output_dir: Path = Path(args.output)

    if args.save_in_dir:
        subdir_name = extract_item_slug_from_url(item_url)
        output_dir /= subdir_name

    downloader = Downloader(
        client_factory=VintedClientFactory(),
        writer=FileWriter(output_dir=output_dir)
    )
    try:
        downloader.download(
            item_url=item_url,
            download_seller_profile=download_seller_profile,
            download_all_seller_items=args.all_items,
        )
    except (ItemUnavailableError, requests.RequestException) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


def extract_details_from_html_with_dto(
        html_content: str
    ) -> dict[str, Any] | None:
    def extract_item_dto_data(html: str) -> str | None:
        regex = r"<script\b[^>]*>self\.__next_f\.push\((.*?)\)<\/script>"
        matches = re.finditer(regex, html, re.DOTALL)

        for match in matches:
            content = match.group(1)
            if "itemDto" in content:
                return content
        return None

    array_str = extract_item_dto_data(html_content)
    if array_str is None:
        return None

    array = json.loads(array_str)
    json_data = None
    for item in array:
        if isinstance(item, str) and "itemDto" in item:
            item = re.sub(r"^[a-zA-Z0-9]+:", "", item)
            json_data = json.loads(item)
            break

    if json_data:
        for x in json_data:
            assert isinstance(x, list)
            for y in x:
                if isinstance(y, dict) and "itemDto" in y:
                    data = y["itemDto"]
                    assert isinstance(data, dict)
                    return data
    return None


def extract_details_from_html_with_full_size_url(
        html_content: str
    ) -> dict[str, Any] | None:
    def get_item_dict(
            data: dict[str, Any] | list[Any]
        ) -> dict[str, Any] | None:
        if isinstance(data, dict):
            # Fast path kept from the original: item wrapped in a
            # {"value": {...}} node.
            value = data.get("value")
            if isinstance(value, dict) and isinstance(
                value.get("photos"), list
            ):
                return value
            # Newer payloads: the item dict appears directly (e.g. under
            # a "data" key) - recognize it by shape instead of wrapper.
            if isinstance(data.get("photos"), list) and "title" in data:
                return data
            for child in data.values():
                if isinstance(child, (dict, list)):
                    if res := get_item_dict(child):
                        return res
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    if res := get_item_dict(item):
                        return res
        return None

    regex = r"self\.__next_f\.push\(\[(.*?)\]\)"
    matches = re.finditer(regex, html_content, re.DOTALL)

    for match in matches:
        try:
            # Wrap payload in [] to make it a valid JSON list for parsing
            raw_payload = f"[{match.group(1)}]"
            payload_parts = json.loads(raw_payload)

            for part in payload_parts:
                if not isinstance(part, str):
                    continue
                
                # Strip Next.js payload prefix to get the valid JSON structure
                json_str = re.sub(r"^[a-f0-9]+:", "", part)
                
                try:
                    data = json.loads(json_str)
                    found = get_item_dict(data)
                    
                    if found:
                        # VALIDATION: Check if photos is a list
                        if isinstance(found.get('photos'), list):
                            return found
                        else:
                            continue
                except json.JSONDecodeError:
                    continue
        except Exception:
            continue
    return None


def iter_flight_json(html_content: str) -> Generator[Any, None, None]:
    """Yield every JSON value embedded in the Next.js flight data.

    The page streams React Server Components data as
    ``self.__next_f.push([1, "<id>:<json>\\n<id>:<json>..."])`` script
    tags. Each line of the pushed string is ``<hex id>:<json>``; lines
    whose body isn't JSON (module references like ``I[...]``) are
    skipped.
    """
    regex = r"<script\b[^>]*>self\.__next_f\.push\((.*?)\)</script>"
    for match in re.finditer(regex, html_content, re.DOTALL):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, list):
            continue
        for part in payload:
            if not isinstance(part, str):
                continue
            for line in part.split("\n"):
                body_match = re.match(r"^[0-9a-f]+:(.*)$", line)
                if body_match is None:
                    continue
                body = body_match.group(1)
                if not body or body[0] not in "[{":
                    continue
                try:
                    yield json.loads(body)
                except json.JSONDecodeError:
                    continue


def _find_photo_bearing_dicts(node: Any, found: list[dict[str, Any]]) -> None:
    if isinstance(node, dict):
        photos = node.get("photos")
        if (
            isinstance(photos, list)
            and photos
            and all(isinstance(p, dict) and "url" in p for p in photos)
        ):
            found.append(node)
        for child in node.values():
            _find_photo_bearing_dicts(child, found)
    elif isinstance(node, list):
        for child in node:
            _find_photo_bearing_dicts(child, found)


ITEM_FLAG_KEYS = (
    "can_buy", "is_reserved", "is_closed", "is_hidden", "is_draft",
    "status", "item_closing_action",
)


def _find_item_flags(node: Any, item_id: int, found: dict[str, Any]) -> None:
    """Collect sale-state flags from any flight dict describing the item."""
    if isinstance(node, dict):
        node_id = node.get("id", node.get("item_id"))
        if node_id is not None and str(node_id) == str(item_id):
            for key in ITEM_FLAG_KEYS:
                if key in node and not isinstance(node[key], (dict, list)):
                    found.setdefault(key, node[key])
        for child in node.values():
            _find_item_flags(child, item_id, found)
    elif isinstance(node, list):
        for child in node:
            _find_item_flags(child, item_id, found)


def extract_item_from_flight_data(
        html_content: str, item_id: int | None = None
    ) -> dict[str, Any] | None:
    """Find the item's photo list inside the flight data.

    The page embeds the item with its photos in the classic API shape
    (``{"id", "title", "price", "seller_id", "photos": [{"id", "url",
    "width", "height", "is_main", "thumbnails": [...]}]}``), minus the
    ``full_size_url`` field: ``url`` is the 800px rendition while
    ``width``/``height`` describe the stored original. Several objects
    carry the photos (the item itself, gallery plugins); they are
    merged, item first. Objects belonging to other items (the seller's
    other listings) are skipped when ``item_id`` is known.
    """
    candidates: list[dict[str, Any]] = []
    flags: dict[str, Any] = {}
    for value in iter_flight_json(html_content):
        _find_photo_bearing_dicts(value, candidates)
        if item_id is not None:
            _find_item_flags(value, item_id, flags)

    matching: list[dict[str, Any]] = []
    for node in candidates:
        node_id = node.get("id", node.get("item_id"))
        if item_id is not None and node_id is not None:
            if str(node_id) != str(item_id):
                continue
        matching.append(node)
    if not matching:
        return None

    # the item object itself (has a title) wins over gallery plugins
    matching.sort(key=lambda n: 0 if "title" in n else 1)
    result: dict[str, Any] = {}
    for node in matching:
        for key, value in node.items():
            result.setdefault(key, value)
    for key, value in flags.items():
        result.setdefault(key, value)
    return result


def extract_details_from_html_page(
        html_content: str, item_id: int | None = None
    ) -> dict[str, Any] | None:
    """Build item data from the server-rendered item page.

    Current Vinted pages don't embed the raw item JSON anymore. They do
    contain: a JSON-LD Product block (title, description, price), the
    item photos as <img data-testid="item-photo-N--img"> tags (800px
    renditions), the seller's /member/<id> link, their username and
    avatar. The flight data additionally carries the complete photo
    list with the originals' dimensions. That is enough to rebuild an
    item dict in the shape the rest of this script expects.
    """
    data: dict[str, Any] = {}

    # --- JSON-LD Product block: title, description, price
    for match in re.finditer(
        r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
        html_content,
        re.DOTALL,
    ):
        try:
            ld = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        nodes = ld if isinstance(ld, list) else [ld]
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "Product":
                data["title"] = str(node.get("name", ""))
                data["description"] = str(node.get("description", ""))
                offers = node.get("offers")
                if isinstance(offers, dict):
                    data["price"] = {
                        "amount": offers.get("price"),
                        "currency_code": offers.get("priceCurrency"),
                    }
                break
        if "title" in data:
            break

    # --- fallbacks from OpenGraph tags
    if not data.get("title"):
        og_title = re.search(
            r'<meta property="og:title" content="([^"]*)"', html_content
        )
        if og_title:
            data["title"] = re.sub(
                r"\s*\|\s*Vinted\s*$", "", unescape(og_title.group(1))
            )

    # --- item photos, in page order, deduplicated (the page renders a
    # mobile and a desktop gallery with the same images)
    photos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in re.finditer(r"<img\b[^>]*>", html_content):
        tag = match.group(0)
        if 'data-testid="item-photo-' not in tag:
            continue
        src = re.search(r'src="([^"]+)"', tag)
        if src is None:
            continue
        url = unescape(src.group(1))
        if url not in seen:
            seen.add(url)
            photos.append({"url": url})
    if photos:
        data["photos"] = photos

    # --- seller: /member/<id> link, username, avatar
    member = re.search(r'href="/member/(\d+)"', html_content)
    if member:
        user: dict[str, Any] = {"id": int(member.group(1))}
        username = re.search(
            r'data-testid="profile-username"[^>]*>([^<]+)<', html_content
        )
        if username:
            user["login"] = unescape(username.group(1)).strip()
        # the avatar is the first image inside the seller card, right
        # after the /member/<id> link
        region = html_content[member.start():member.start() + 2000]
        avatar = re.search(r'<img[^>]*src="([^"]+)"', region)
        if avatar:
            user["photo"] = {"full_size_url": unescape(avatar.group(1))}
        data["user"] = user

    # --- flight data: the complete photo list (even when the gallery
    # only renders the first few), plus id, price and seller id
    flight = extract_item_from_flight_data(html_content, item_id)
    if flight:
        flight_photos = flight.get("photos")
        if isinstance(flight_photos, list) and len(flight_photos) >= len(
            photos
        ):
            data["photos"] = flight_photos
        for key in ("title", "description", "price"):
            if key in flight and not data.get(key):
                data[key] = flight[key]
        for key in ITEM_FLAG_KEYS:
            if key in flight:
                data.setdefault(key, flight[key])
        if "id" in flight and not data.get("id"):
            try:
                data["id"] = int(flight["id"])
            except (TypeError, ValueError):
                pass
        seller_id = flight.get("seller_id")
        if seller_id is not None:
            user = data.setdefault("user", {})
            if not user.get("id"):
                try:
                    user["id"] = int(seller_id)
                except (TypeError, ValueError):
                    pass

    if not data.get("title") and not data.get("photos"):
        return None
    data.setdefault("photos", [])
    return data


def get_item_id(item_url: str) -> int:
    match = re.search(r"/items/(\d+)", item_url)
    if match is None:
        raise RuntimeError("Unable to find item_url")
    item_id = int(match.group(1))
    return item_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="vinted_downloader",
        description="Download item images and seller data from Vinted"
    )

    parser.add_argument(
        "item_url",
        help="URL of the item to download"
    )

    parser.add_argument(
        "-o", "--output",
        default=".",
        help="Directory where files will be saved (default: current directory)"
    )

    parser.add_argument(
        "-s", "--seller",
        action="store_true",
        help="Also download the seller's profile picture"
    )

    parser.add_argument(
        "-a", "--all-items",
        action="store_true",
        help="Download all items listed by the seller"
    )

    parser.add_argument(
        "-d", "--save-in-dir",
        action="store_true",
        help=(
            "Save files in a separate subdirectory of the output directory. "
            "The folder name is based on the item id and title."
        )
    )

    args = parser.parse_args()

    return args


def extract_item_slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    return Path(parsed.path).name


if __name__ == "__main__":
    code = main()
    sys.exit(code)
