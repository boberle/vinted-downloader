from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from vinted_downloader import get_image_urls, get_seller_url


def _get_soup(file: str) -> BeautifulSoup:
    html = (Path(__file__).parent / "testdata" / file).read_text()
    return BeautifulSoup(html, "lxml")


@pytest.fixture
def main_page_soup_1_image() -> BeautifulSoup:
    return _get_soup("20230405-1_image.html")


@pytest.fixture
def main_page_soup_2_images() -> BeautifulSoup:
    return _get_soup("20230405-2_images.html")


@pytest.fixture
def main_page_soup_multiple_images() -> BeautifulSoup:
    return _get_soup("20230405-multiple_images.html")


def test_get_1_image_url(main_page_soup_1_image: BeautifulSoup) -> None:
    urls = get_image_urls(main_page_soup_1_image)
    assert len(urls) == 1
    assert (
        urls[0]
        == "https://images1.vinted.net/t/03_01405_9JY2uYeCjxhTp9jTd4qBb9fU/f800/1680635440.jpeg?s=dd20ffc1ff5924791a066aacd41289175f6a27e8"
    )


def test_get_2_images_urls(main_page_soup_2_images: BeautifulSoup) -> None:
    urls = get_image_urls(main_page_soup_2_images)
    assert len(urls) == 2
    assert (
        urls[0]
        == "https://images1.vinted.net/t/03_00b7c_KccCjUsHdvRX9wv2pjFPFSRy/f800/1680361243.jpeg?s=faa4e638193a44f9def2f2ecee6bcc56c77ecaa2"
    )
    assert (
        urls[1]
        == "https://images1.vinted.net/t/03_01116_TGmUy4Lwnyc8nHupN7JLjiuV/f800/1680361243.jpeg?s=ad5645755da06ed646a913efa3542c5abc014e2b"
    )


def test_get_multiple_image_urls(main_page_soup_multiple_images: BeautifulSoup) -> None:
    urls = get_image_urls(main_page_soup_multiple_images)
    assert len(urls) == 19
    assert urls == [
        "https://images1.vinted.net/t/03_00209_zv1s8j4GzfDAfvJbxF1So6NW/f800/1679679459.jpeg?s=3d16d3c4c25e78f94c9e828783b2e37554db8c4f",
        "https://images1.vinted.net/t/03_01303_fUR7Et3tMmptew974LQXihCR/f800/1679679459.jpeg?s=ab0f6b4361a5abe5a0275177995ced2d07628099",
        "https://images1.vinted.net/t/02_00005_T6ZDNkJhPT1QQhJphaRSaz5d/f800/1679679459.jpeg?s=171eaddcbdab4dd0fb7df19e1cf14a0dac4a3019",
        "https://images1.vinted.net/t/03_002be_yHeGtH5zfJAn1DQUGezN4W1f/f800/1679679459.jpeg?s=b5272fed403e21c2dc451278fa2a0abc96833875",
        "https://images1.vinted.net/t/03_01f95_WQB9nX6AsAttXEWLUFpNeFDF/f800/1679679459.jpeg?s=3ddaea3fe4a23e169e9a10a5a7f6ff2b6a316bf8",
        "https://images1.vinted.net/t/01_01254_gji5LtwXAkFs42Bvh67DjdMa/f800/1679679459.jpeg?s=ba337df9ee2857c48cf88621a11704eda9edb3cf",
        "https://images1.vinted.net/t/02_00994_dg3D2LaMx3U53gZcrSa9kHey/f800/1679679459.jpeg?s=fa02f9858ae4e6a5a49c33be08cedbecde0f8254",
        "https://images1.vinted.net/t/01_01c05_Y85AnVPxXsF7Zz5EcF56XuSb/f800/1679679459.jpeg?s=435fdd6b368a8f608c1145b31d5c7f3280843b2a",
        "https://images1.vinted.net/t/03_00dea_EYgfAaneRxu8b5UZ9ZRwrQbc/f800/1679679459.jpeg?s=9fb0dc7eed1efb8883c971a569c7c227743b526f",
        "https://images1.vinted.net/t/01_0174b_NcMzeEKwjDKaXiXbk3gnGZMZ/f800/1679679459.jpeg?s=94a7633f31948e6016660bad236796c8a3859f3b",
        "https://images1.vinted.net/t/03_01bf1_SLTekSiRC9W8hwB4U9WnKzV9/f800/1679679459.jpeg?s=bad9d7a0f514d54888d5c2e92c3b183e626cc460",
        "https://images1.vinted.net/t/02_01e1e_fV7AheoxuV4PUyHwjfgrjrQK/f800/1679679459.jpeg?s=e84c4b15b010055d3c847f8cf797b6152b194cec",
        "https://images1.vinted.net/t/01_01254_gji5LtwXAkFs42Bvh67DjdMa/f800/1679679459.jpeg?s=ba337df9ee2857c48cf88621a11704eda9edb3cf",
        "https://images1.vinted.net/t/02_00994_dg3D2LaMx3U53gZcrSa9kHey/f800/1679679459.jpeg?s=fa02f9858ae4e6a5a49c33be08cedbecde0f8254",
        "https://images1.vinted.net/t/01_01c05_Y85AnVPxXsF7Zz5EcF56XuSb/f800/1679679459.jpeg?s=435fdd6b368a8f608c1145b31d5c7f3280843b2a",
        "https://images1.vinted.net/t/03_00dea_EYgfAaneRxu8b5UZ9ZRwrQbc/f800/1679679459.jpeg?s=9fb0dc7eed1efb8883c971a569c7c227743b526f",
        "https://images1.vinted.net/t/01_0174b_NcMzeEKwjDKaXiXbk3gnGZMZ/f800/1679679459.jpeg?s=94a7633f31948e6016660bad236796c8a3859f3b",
        "https://images1.vinted.net/t/03_01bf1_SLTekSiRC9W8hwB4U9WnKzV9/f800/1679679459.jpeg?s=bad9d7a0f514d54888d5c2e92c3b183e626cc460",
        "https://images1.vinted.net/t/02_01e1e_fV7AheoxuV4PUyHwjfgrjrQK/f800/1679679459.jpeg?s=e84c4b15b010055d3c847f8cf797b6152b194cec",
    ]


def test_get_seller_url(main_page_soup_1_image: BeautifulSoup) -> None:
    url = "https://www.vinted.fr/anything/"
    seller_url = get_seller_url(url, main_page_soup_1_image)
    assert seller_url == "https://www.vinted.fr/member/128814359"


def test_get_seller_url_test2(main_page_soup_2_images: BeautifulSoup) -> None:
    url = "https://www.vinted.fr/anything/"
    seller_url = get_seller_url(url, main_page_soup_2_images)
    assert seller_url == "https://www.vinted.fr/member/25501919"
