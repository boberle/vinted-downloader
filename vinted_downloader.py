from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from abc import abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast, Protocol, Generator
from urllib.parse import urlparse

import requests

AUTHOR_EMAIL = "contact@boberle.com"
ERROR_FILE = "vinted_product_downloader_error.txt"
SNAP = [1, 2, 3]


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

            for i, photo_bytes in enumerate(
                client.download_photos(*details.full_size_photo_urls)
            ):
                self.writer.write_bytes(
                    Path(f"photo_{i:02d}.webp"), photo_bytes
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
            "User-Agent": "Mozilla/5.0",
        })
        # Connect the first time to get the anonymous cookie auth
        self.session.get(f"https://www.vinted.{self.vinted_tld}") 

    def download_item_details(self, item_url: str) -> dict[str, Any]:
        self._nap()
        print("downloading details from '%s'" % item_url)
        response = self.session.get(item_url)
        try:
            response_text = response.text
            data = extract_details_from_html_with_dto(response_text)
            if data is None:
                data = extract_details_from_html_with_full_size_url(
                    response_text
                )
                if data is None:
                    raise ValueError(
                        "Unable to extract product details from the HTML"
                    )
                print("Found data with the 'full_size_url' method")
            else:
                print("Found data with the 'itemDto' method")
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

    def download_items_details(self, profile_id: int) -> dict[str, Any]:
        self._nap()
        self.session.get(
            f"https://www.vinted.{self.vinted_tld}/member/{profile_id}"
        )
        url = (
            f"https://www.vinted.{self.vinted_tld}/api/v2/wardrobe/{profile_id}/items"
        )
        response = self.session.get(
            url,
            headers={
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"https://www.vinted.{self.vinted_tld}/member/{profile_id}",
            }
        )
        data = cast(dict[str, Any], response.json())
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
    if download_seller_profile:
        raise RuntimeError("--seller option is disabled for now")
    output_dir: Path = Path(args.output)

    if args.save_in_dir:
        subdir_name = extract_item_slug_from_url(item_url)
        output_dir /= subdir_name

    downloader = Downloader(
        client_factory=VintedClientFactory(),
        writer=FileWriter(output_dir=output_dir)
    )
    downloader.download(
        item_url=item_url,
        download_seller_profile=download_seller_profile,
        download_all_seller_items=args.all_items,
    )

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


def get_item_id(item_url: str) -> int:
    match = re.search(r"(?<=/)\d+(?=-)", item_url)
    if match is None:
        raise RuntimeError("Unable to find item_url")
    item_id = int(match.group(0))
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
