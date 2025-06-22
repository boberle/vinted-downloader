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

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
SNAP = [1, 2, 3]


@dataclass
class Summary:
    source: str
    title: str
    description: str
    seller: str
    seller_id: int
    last_logged_in: str

    def __str__(self) -> str:
        summary = f"source: {self.source}\n"
        summary += f"title: {self.title}\n"
        summary += f"description: {self.description}\n"
        summary += f"seller: {self.seller}\n"
        summary += f"seller id: {self.seller_id}\n"
        summary += f"seller last logged in: {self.last_logged_in}\n"
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

        self.writer.write_text(Path("item.json"), json.dumps(details.data))
        summary = Summary(
            source=item_url,
            title=details.title,
            description=details.description,
            seller=details.seller,
            seller_id=details.seller_id,
            last_logged_in=details.seller_last_logged_in,
        )
        self.writer.write_text(Path("item_summary"), str(summary))

        if download_all_seller_items:
            items_id = []
            data = client.download_items_details(details.seller_id)

            for item in data["items"]:
                items_id.append(item["id"])

            for item_id in items_id:
                details = Details(client.download_item_details(item_url=item_url))
                for i, photo_bytes in enumerate(
                    client.download_photos(*details.full_size_photo_urls)
                ):
                    self.writer.write_bytes(
                        Path(f"photo_{i}_{item_id}.jpg"), photo_bytes
                    )
        else:
            for i, photo_bytes in enumerate(
                client.download_photos(*details.full_size_photo_urls)
            ):
                self.writer.write_bytes(Path(f"photo_{i}.jpg"), photo_bytes)

        if download_seller_profile and details.seller_photo_url:
            photo_bytes = client.download_photo(details.seller_photo_url)
            self.writer.write_bytes(Path("seller.jpg"), photo_bytes)

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
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "fr-FR,fr;q=0.5",
        }
        self.session = requests.Session()
        self.session.headers.update(headers)
        # connect the first time to Vinted to get the anonymous cookie auth
        self.session.get(f"https://www.vinted.{self.vinted_tld}")

    def download_item_details(self, item_url: str) -> dict[str, Any]:
        self._nap()
        print("downloading details from '%s'" % item_url)
        response = self.session.get(item_url)
        try:
            data = extract_details_from_html(response.text)
            if data is None:
                raise ValueError("Unable to extract product details from the HTML")
            return data
        except json.JSONDecodeError:
            open("vinted_product_downloader_error.txt", "wb").write(response.content)
            print(
                "=========\n"
                "An error occurred while decoding the product details.\n"
                "The content of the response has been saved in vinted_product_downloader_error.txt.\n"
                "You can review the file, or send it to the developers at contact@boberle.com\n"
                "for further assistance.\n"
                "========="
            )
            sys.exit(1)

    def download_items_details(self, profile_id: int) -> dict[str, Any]:
        self._nap()
        url = f"https://www.vinted.{self.vinted_tld}/api/v2/users/{profile_id}/items?localize=false"  # https://www.vinted.fr/api/v2/users/88485782/items?page=1&per_page=20&order=relevance
        data = cast(dict[str, Any], self.session.get(url).json())
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
        (self.output_dir / file).write_text(data, encoding="utf-8")

    def write_bytes(self, file: Path, data: bytes) -> None:
        self._create()
        (self.output_dir / file).write_bytes(data)

    def _create(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class Details:
    data: dict[str, Any]

    @property
    def title(self) -> str:
        return str(self.data["title"])

    @property
    def description(self) -> str:
        return str(self.data.get("description", ""))

    @property
    def seller(self) -> str:
        try:
            return str(self.data["user"]["login"])
        except KeyError:
            return ""

    @property
    def seller_id(self) -> int:
        try:
            return cast(int, self.data["user"]["id"])
        except KeyError:
            return cast(int, self.data["seller_id"])

    @property
    def seller_last_logged_in(self) -> str:
        try:
            return str(
                self.data["user"].get("last_logged_on_ts")
                or self.data["user"]["last_loged_on_ts"]
            )
        except KeyError:
            return ""

    @property
    def full_size_photo_urls(self) -> list[str]:
        return [photo["full_size_url"] for photo in self.data["photos"]]

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
    output_dir: Path = Path(args.output_dir)

    if args.save_in_dir:
        subdir_name = extract_item_slug_from_url(item_url)
        output_dir /= subdir_name

    downloader = Downloader(
        client_factory=VintedClientFactory(), writer=FileWriter(output_dir=output_dir)
    )
    downloader.download(
        item_url=item_url,
        download_seller_profile=download_seller_profile,
        download_all_seller_items=args.all,
    )

    return 0


def extract_details_from_html(html_content: str) -> dict[str, Any] | None:

    def get_item_dict(data: dict[str, Any] | list[Any]) -> dict[str, Any] | None:
        if isinstance(data, dict) and "item" in data:
            return cast(dict[str, Any], data["item"])

        if isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    if res := get_item_dict(item):
                        return res
        elif isinstance(data, dict):
            for key, value in data.items():
                assert not isinstance(key, (dict, list))
                if isinstance(value, (dict, list)):
                    if res := get_item_dict(value):
                        return res
        else:
            assert False, "Invalid data type"
        return None

    regex = r"<script\b[^>]*>self\.__next_f\.push\((.*?)\)<\/script>"
    matches = re.finditer(regex, html_content, re.DOTALL)
    for match in matches:
        if "full_size_url" not in match.group(1):
            continue
        outer_list: list[Any] = json.loads(match.group(1))
        for outer_item in outer_list:
            if not isinstance(outer_item, str):
                continue
            item, n = re.subn(r"^[a-zA-Z0-9]+:\[", "[", outer_item)
            if n > 0:
                found = get_item_dict(json.loads(item))
                if found:
                    return found
    return None


def get_item_id(item_url: str) -> int:
    match = re.search(r"(?<=/)\d+(?=-)", item_url)
    if match is None:
        raise RuntimeError("Unable to find item_url")
    item_id = int(match.group(0))
    return item_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="vinted_downloader")

    parser.add_argument("item_url", default="", help="url of an item")
    parser.add_argument(
        "-o",
        dest="output_dir",
        required=False,
        default=".",
        help="output directory (default is current directory)",
    )
    parser.add_argument(
        "--seller",
        default=False,
        action="store_true",
        help="download seller picture profile",
    )
    parser.add_argument(
        "--all",
        default=False,
        action="store_true",
        help="download all seller items",
    )
    parser.add_argument(
        "--save-in-dir",
        default=False,
        action="store_true",
        help=(
            "save files in a subdirectory of the `-o` option directory. "
            "The subdirectory is named with the item title and id"
        ),
    )
    args = parser.parse_args()
    return args


def extract_item_slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    return Path(parsed.path).name


if __name__ == "__main__":
    code = main()
    sys.exit(code)
