from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator

from vinted_downloader import Client, ClientFactory, Writer


@dataclass
class TestClient(Client):
    __test__ = False
    details: dict[int, dict[str, Any]]
    downloads: dict[str, bytes]

    def download_item_details(self, item_id: int) -> dict[str, Any]:
        return self.details[item_id]

    def download_items_details(self, profile_id: int) -> dict[str, Any]:
        raise NotImplementedError

    def download_photos(self, *urls: str) -> Generator[bytes, None, None]:
        for url in urls:
            yield self.download_photo(url)

    def download_photo(self, url: str) -> bytes:
        return self.downloads[url]


@dataclass
class TestClientFactory(ClientFactory):
    __test__ = False
    details: dict[int, dict[str, Any]]
    downloads: dict[str, bytes]

    def build(self, vinted_tld: str) -> Client:
        return TestClient(details=self.details, downloads=self.downloads)


@dataclass
class TestWriter(Writer):
    __test__ = False
    data: dict[Path, str | bytes] = field(default_factory=dict)

    def write_text(self, file: Path, data: str) -> None:
        self.data[file] = data

    def write_bytes(self, file: Path, data: bytes) -> None:
        self.data[file] = data
