import argparse
import json
import random
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import requests

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
SNAP = [1, 2, 3]


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
        path.write_text(summary, encoding="utf-8")


def main() -> int:
    args = parse_args()
    item_url: str = args.item_url
    download_seller_profile: bool = args.seller
    output_dir: Path = Path(args.output_dir)

    match = re.search(r"(?<=/)\d+(?=-)", item_url)
    if match is None:
        raise RuntimeError("Unable to find item_url")
    item_id = int(match.group(0))

    match = re.search(r"(?<=\.)[a-z.]+(?=/)", item_url)
    if match is None:
        raise RuntimeError("Unable to find vinted tld")
    vinted_tld = match.group(0)

    client = VintedClient(vinted_tld=vinted_tld)
    details = Details(client.download_item_details(item_id=item_id))

    save_json(output_dir / "item.json", details.data)
    Summary(
        source=item_url,
        title=details.title,
        description=details.description,
        seller=details.seller,
        seller_id=details.seller_id,
        last_logged_in=details.seller_last_logged_in,
    ).save(output_dir / "item_summary")

    download_photos(
        output_dir, "photo_{index}.jpg", client, *details.full_size_photo_urls
    )
    if download_seller_profile and details.seller_photo_url:
        download_photos(output_dir, "seller.jpg", client, details.seller_photo_url)

    return 0


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
    args = parser.parse_args()
    return args


@dataclass
class VintedClient:
    vinted_tld: str
    snap: list[int] | None = field(default_factory=lambda: SNAP)

    def __post_init__(self) -> None:
        headers = {
            "User-Agent": "My User Agent 1.0",
            "Accept-Language": "fr-FR,fr;q=0.5",
        }
        self.session = requests.Session()
        self.session.headers.update(headers)
        # connect the first time to Vinted to get the anonymous cookie auth
        self.session.get(f"https://www.vinted.{self.vinted_tld}")

    def download_item_details(self, item_id: int) -> dict[str, Any]:
        self._snap()
        url = f"https://www.vinted.{self.vinted_tld}/api/v2/items/{item_id}?localize=false"
        print("downloading details from '%s'" % url)
        data = cast(dict[str, Any], self.session.get(url).json())
        return data

    def download_resource(self, url: str) -> bytes:
        self._snap()
        print("downloading resource from '%s'" % url)
        resource = self.session.get(url).content
        return resource

    def _snap(self) -> None:
        if self.snap is not None and len(self.snap):
            time.sleep(random.choice(self.snap))


def download_photos(
    output_dir: Path, template_name: str, client: VintedClient, *urls: str
) -> None:
    for i, url in enumerate(urls):
        data = client.download_resource(url)
        fn = template_name.format(index=i)
        (output_dir / fn).write_bytes(data)


def save_json(path: Path, data: dict[str, Any]) -> None:
    json.dump(data, path.open("w", encoding="utf-8"), indent=2)


@dataclass
class Details:
    data: dict[str, Any]

    @property
    def title(self) -> str:
        return str(self.data["item"]["title"])

    @property
    def description(self) -> str:
        return str(self.data["item"]["description"])

    @property
    def seller(self) -> str:
        return str(self.data["item"]["user"]["login"])

    @property
    def seller_id(self) -> int:
        return cast(int, self.data["item"]["user"]["id"])

    @property
    def seller_last_logged_in(self) -> str:
        # some typo in the json key...
        return str(
            self.data["item"]["user"].get("last_logged_on_ts")
            or self.data["item"]["user"]["last_loged_on_ts"]
        )

    @property
    def full_size_photo_urls(self) -> list[str]:
        return [photo["full_size_url"] for photo in self.data["item"]["photos"]]

    @property
    def seller_photo_url(self) -> str | None:
        try:
            url = self.data["item"]["user"]["photo"]["full_size_url"]
        except (KeyError, TypeError):
            return None
        else:
            return url or None


if __name__ == "__main__":
    code = main()
    sys.exit(code)
