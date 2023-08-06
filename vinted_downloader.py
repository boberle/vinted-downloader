import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
SNAP = (1, 2, 3)


class ItemDetailsNotFound(Exception):
    ...


@dataclass
class Summary:
    source: str
    title: str
    description: str
    seller: str
    seller_id: int
    last_logged_in: str

    def save(self, path: Path) -> None:
        summary = f"source: {self.source}\n"
        summary += f"title: {self.title}\n"
        summary += f"description: {self.description}\n"
        summary += f"seller: {self.seller}\n"
        summary += f"seller id: {self.seller_id}\n"
        summary += f"seller last logged in: {self.last_logged_in}\n"
        path.write_text(summary)


def main() -> int:
    args = parse_args()
    source: str | Path = (
        args.source if args.source.startswith("http") else Path(args.source)
    )
    download_seller_profile: bool = args.seller
    output_dir: Path = Path(args.output_dir)

    html = load_html(source)
    details = Details(html)

    save_json(output_dir / "item.json", details.json)
    Summary(
        source=str(source),
        title=details.title,
        description=details.description,
        seller=details.seller,
        seller_id=details.seller_id,
        last_logged_in=details.seller_last_logged_in,
    ).save(output_dir / "item_summary")

    download_photos(output_dir, "photo_{index}.jpg", *details.full_size_photo_urls)
    if download_seller_profile and details.seller_photo_url:
        download_photos(output_dir, "seller.jpg", details.seller_photo_url)

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="vinted_downloader")

    parser.add_argument("source", default="", help="url or file")
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
    args = parser.parse_args()
    return args


def download(url: str) -> bytes:
    print("downloading from '%s'" % url)
    if len(SNAP):
        time.sleep(random.choice(SNAP))
    request = urllib.request.Request(
        url,
        data=None,
        headers={
            "User-Agent": USER_AGENT,
        },
    )
    fh = urllib.request.urlopen(request)
    return cast(bytes, fh.read())


def download_photos(output_dir: Path, template_name: str, *urls: str) -> None:
    for i, url in enumerate(urls):
        data = download(url)
        fn = template_name.format(index=i)
        (output_dir / fn).write_bytes(data)


def save_json(path: Path, data: dict[Any, Any]) -> None:
    json.dump(data, path.open("w"), indent=2)


def load_html(source: Path | str) -> str:
    if isinstance(source, Path):
        html = source.read_text()
    else:
        html = download(source).decode("utf-8")
    return html


class Details:
    def __init__(self, html: str):
        self._json_data = self._build_from_html(html)

    def _build_from_html(self, html: str) -> dict[Any, Any]:
        soup = BeautifulSoup(html, "lxml")
        return self._extract_item_details_json(soup)

    def _extract_item_details_json(self, soup: BeautifulSoup) -> dict[Any, Any]:
        tag = soup.find(
            "script",
            attrs={
                "type": "application/json",
                "class": "js-react-on-rails-component",
                "data-component-name": "ItemDetails",
            },
        )
        if not tag:
            raise ItemDetailsNotFound

        try:
            return cast(dict[Any, Any], json.loads(tag.text))
        except json.JSONDecodeError:
            raise ItemDetailsNotFound

    @property
    def json(self) -> dict[Any, Any]:
        return self._json_data.copy()

    @property
    def title(self) -> str:
        return str(self._json_data["item"]["title"])

    @property
    def description(self) -> str:
        return str(self._json_data["item"]["description"])

    @property
    def seller(self) -> str:
        return str(self._json_data["item"]["user"]["login"])

    @property
    def seller_id(self) -> int:
        return cast(int, self._json_data["item"]["user"]["id"])

    @property
    def seller_last_logged_in(self) -> str:
        return str(self._json_data["item"]["user"]["last_logged_on_ts"])

    @property
    def full_size_photo_urls(self) -> list[str]:
        return [photo["full_size_url"] for photo in self._json_data["item"]["photos"]]

    @property
    def seller_photo_url(self) -> str | None:
        try:
            url = self._json_data["item"]["user"]["photo"]["full_size_url"]
        except KeyError:
            return None
        else:
            return url or None


if __name__ == "__main__":
    code = main()
    sys.exit(code)
