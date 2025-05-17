import json
from pathlib import Path
from typing import Any, cast

import pytest

from conftest import TestWriter, TestClientFactory
from vinted_downloader import (
    Downloader,
    Details,
    extract_item_slug_from_url,
    FileWriter,
    get_item_id,
)


@pytest.mark.parametrize(
    "url,exp",
    [
        [
            "https://www.vinted.fr/items/3397265884-la-voleuse-de-livres?referrer=catalog",
            3397265884,
        ],
        [
            "https://www.vinted.fr/items/3682535752-jeu-pc?referrer=catalog",
            3682535752,
        ],
    ],
)
def test_downloader_get_item_id(url: str, exp: int) -> None:
    assert get_item_id(url) == exp


@pytest.mark.parametrize(
    "url,exp",
    [
        [
            "https://www.vinted.fr/items/3397265884-la-voleuse-de-livres?referrer=catalog",
            "fr",
        ],
        [
            "https://www.vinted.de/items/3604002439-haba-meine-ersten-puzzles-baustelle?referrer=catalog",
            "de",
        ],
        [
            "https://www.vinted.co.uk/items/3597904925-dobble-classic-mini-travel-game?referrer=catalog",
            "co.uk",
        ],
    ],
)
def test_downloader_get_vinted_tld(url: str, exp: str) -> None:
    assert Downloader._get_vinted_tld(url) == exp


@pytest.fixture
def testdata_dir() -> Path:
    return Path(__file__).parent / "testdata"


@pytest.fixture
def json_data_1(testdata_dir: Path) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.load((testdata_dir / "item.json").open()),
    )


def test_downloader_download(json_data_1: dict[str, Any]) -> None:
    client_factory = TestClientFactory(
        details={123456: json_data_1},
        downloads={
            "https://images1.vinted.net/tc/123.jpeg?s=1a2b1": b"1",
            "https://images1.vinted.net/tc/123.jpeg?s=1a2b2": b"2",
            "https://images1.vinted.net/tc/123.jpeg?s=1a2b3": b"3",
            "https://images1.vinted.net/tc/123.jpeg?s=1a2b4": b"4",
            "https://images1.vinted.net/tc/123.jpeg?s=1a2b5": b"5",
            "https://images1.vinted.net/tc/123.jpeg?s=1a2b6": b"6",
            "https://images1.vinted.net/tc/123.jpeg?s=1a2b7": b"7",
            "https://images1.vinted.net/tc/123.jpeg?s=1a2b8": b"8",
            "https://images1.vinted.net/tc/123.jpeg?s=1a2b9": b"9",
            "https://images1.vinted.net/tc/123.jpeg?s=1a2b10": b"10",
            "https://images1.vinted.net/tc/321.jpeg?s=3c4d": b"11",
        },
    )
    writer = TestWriter()
    downloader = Downloader(client_factory, writer)
    downloader.download(
        item_url="https://www.vinted.fr/items/123456-foobar?referrer=catalog",
        download_seller_profile=True,
        download_all_seller_items=False,
    )

    summary = """source: https://www.vinted.fr/items/123456-foobar?referrer=catalog
title: The title
description: The description
Another line
seller: me
seller id: 654321
seller last logged in: 2023-10-12T19:28:44+01:00
"""

    exp = {
        Path("item.json"): json.dumps(json_data_1),
        Path("item_summary"): summary,
        Path("photo_0.jpg"): b"1",
        Path("photo_1.jpg"): b"2",
        Path("photo_2.jpg"): b"3",
        Path("photo_3.jpg"): b"4",
        Path("photo_4.jpg"): b"5",
        Path("photo_5.jpg"): b"6",
        Path("photo_6.jpg"): b"7",
        Path("photo_7.jpg"): b"8",
        Path("photo_8.jpg"): b"9",
        Path("photo_9.jpg"): b"10",
        Path("seller.jpg"): b"11",
    }

    assert len(writer.data) == len(exp)
    for k, v in writer.data.items():
        assert exp[k] == v


def test_details(json_data_1: dict[str, Any]) -> None:
    details = Details(json_data_1)
    assert details.title == "The title"
    assert details.description == "The description\nAnother line"
    assert details.seller == "me"
    assert details.seller_id == 654321
    assert details.seller_last_logged_in == "2023-10-12T19:28:44+01:00"
    assert details.seller_photo_url == "https://images1.vinted.net/tc/321.jpeg?s=3c4d"
    assert details.full_size_photo_urls == [
        "https://images1.vinted.net/tc/123.jpeg?s=1a2b1",
        "https://images1.vinted.net/tc/123.jpeg?s=1a2b2",
        "https://images1.vinted.net/tc/123.jpeg?s=1a2b3",
        "https://images1.vinted.net/tc/123.jpeg?s=1a2b4",
        "https://images1.vinted.net/tc/123.jpeg?s=1a2b5",
        "https://images1.vinted.net/tc/123.jpeg?s=1a2b6",
        "https://images1.vinted.net/tc/123.jpeg?s=1a2b7",
        "https://images1.vinted.net/tc/123.jpeg?s=1a2b8",
        "https://images1.vinted.net/tc/123.jpeg?s=1a2b9",
        "https://images1.vinted.net/tc/123.jpeg?s=1a2b10",
    ]


@pytest.mark.parametrize(
    "url,slug",
    [
        (
            "https://www.vinted.fr/items/1234567890-foo-bar?noredirect=1",
            "1234567890-foo-bar",
        ),
        ("https://www.vinted.fr/items/1234567890-foo-bar", "1234567890-foo-bar"),
    ],
)
def test_extract_item_slug_from_url(url: str, slug: str) -> None:
    assert extract_item_slug_from_url(url) == slug


def test_file_writer_writes_in_subdir(tmp_path: Path) -> None:
    url = "https://www.vinted.fr/items/1234567890-foo-bar"
    path = tmp_path / "output" / extract_item_slug_from_url(url)
    writer = FileWriter(path)
    content = b"hello"
    writer.write_bytes(Path("photo_0.jpg"), content)
    assert (
        tmp_path / "output" / "1234567890-foo-bar" / "photo_0.jpg"
    ).read_bytes() == content
