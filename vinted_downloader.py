import argparse
import json
import os
import random
import time
import urllib
import urllib.error
import urllib.request
from argparse import Namespace
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
SNAP = (1, 2, 3, 4, 5, 6)


def download(url: str) -> bytes:
    if len(SNAP):
        print("(zzzzzzz...)")
        time.sleep(random.choice(SNAP))
    try:
        print("Downloading from '%s'" % url)
        request = urllib.request.Request(
            url,
            data=None,
            headers={
                "User-Agent": USER_AGENT,
            },
        )
        fh = urllib.request.urlopen(request)
        return fh.read()
    except urllib.error.URLError:
        print("*** can't read the page '%s' ***" % url)
        raise


def save(data: str | bytes, file: Path) -> None:
    print(f"Saving '{str(file)}'.")
    if isinstance(data, str):
        file.write_text(data)
    else:
        file.write_bytes(data)


def go(
    url: str, dest_dir: Path, driver: str, executable: str, source: Path | None = None
) -> None:
    output_dir = make_directory_from_url(url, dest_dir)
    write_url_in_file(url, output_dir)

    soup = download_and_save_main_page(url, output_dir, source)

    # images
    image_urls = get_image_urls(soup)
    write_image_url_in_file(image_urls, output_dir)
    download_and_save_images(image_urls, output_dir)

    # seller page
    seller_url = get_seller_url(url, soup)
    write_seller_url_in_file(seller_url, output_dir)
    download_and_save_seller_page(seller_url, output_dir)

    # get seller dom via selenium
    seller_soup = get_and_save_seller_html_via_driver(
        seller_url, output_dir, driver, executable
    )
    profile_picture_url = get_seller_profile_picture_url(seller_soup)
    write_seller_profile_url_in_file(profile_picture_url, output_dir)
    download_and_save_profile_picture(profile_picture_url, output_dir)


def make_directory_from_url(url: str, dest_dir: Path) -> Path:
    url = url.rstrip("/")
    parsed = urlparse(url)

    dname = os.path.basename(parsed.path)
    assert dname

    dpath = dest_dir / dname
    if dpath.exists():
        raise FileExistsError(str(dpath))
    dpath.mkdir(parents=True, exist_ok=False)

    return dpath


def write_url_in_file(url: str, output_dir: Path) -> None:
    (output_dir / "url").write_text(url)


def download_and_save_main_page(
    url: str, output_dir: Path, source: Path | None
) -> BeautifulSoup:
    if source:
        main_page = source.read_text()
    else:
        main_page = download(url).decode("utf-8")
    save(main_page, output_dir / "page.html")
    soup = BeautifulSoup(main_page, "lxml")
    return soup


def get_image_urls(soup: BeautifulSoup) -> list[str]:
    image_urls: list[str] = []

    div = soup.find("div", class_="item-photos")
    assert div and isinstance(div, Tag)

    for figure in div.find_all("figure"):
        image_url = figure.a["href"]
        print("Found an image at '%s'" % image_url)
        image_urls.append(image_url)

    # some supplementary images (only the first 5 are shown on the main
    # page) are in a "u-hidden" div (there are several of this kind of div, we
    # want the one with the 'item-description' figures)
    for u_hidden_div in soup.find_all("div", class_="u-hidden"):
        for figure in u_hidden_div.find_all("figure", class_="item-description"):
            image_url = figure.a["href"]
            print("Found a supplementary image at '%s'" % image_url)
            image_urls.append(image_url)

    assert image_urls
    return image_urls


def write_image_url_in_file(urls: list[str], output_dir: Path) -> None:
    (output_dir / "image_urls").write_text("\n".join(urls))


def download_and_save_images(urls: list[str], output_dir: Path) -> None:
    for i, url in enumerate(urls):
        data = download(url)
        save(data, output_dir / f"image_{i}.jpg")


def get_seller_url(url: str, soup: BeautifulSoup) -> str:
    element = soup.find(
        "script",
        attrs={"data-component-name": "ItemUserInfo"},
    )
    assert element and isinstance(element, Tag)
    seller_id = element.string

    assert seller_id
    seller_id = json.loads(seller_id)["user"]["id"]

    parsed = urlparse(url)
    seller_url = f"/member/{seller_id}"
    seller_url = f"{parsed.scheme}://{parsed.netloc}{seller_url}"
    return seller_url


def write_seller_url_in_file(url: str, output_dir: Path) -> None:
    (output_dir / "seller_url").write_text(url)


def download_and_save_seller_page(url: str, output_dir: Path) -> None:
    seller_page = download(url).decode("utf-8")
    save(seller_page, output_dir / "seller.html")


def get_and_save_seller_html_via_driver(
    url: str, output_dir: Path, driver: str, executable: str
) -> BeautifulSoup:
    service = Service(driver)
    options = Options()
    if executable:
        options.binary_location = executable

    ffdriver = webdriver.Firefox(service=service, options=options)
    ffdriver.get(url)

    time.sleep(2)
    html = ffdriver.execute_script("return document.body.outerHTML;")
    save(html, output_dir / "seller_dom.html")
    ffdriver.close()

    soup = BeautifulSoup(html, "lxml")
    return soup


def get_seller_profile_picture_url(soup: BeautifulSoup) -> str:
    picture_url = None
    for img in soup.find_all("img"):
        if "/f800/" not in img["src"]:
            continue
        assert picture_url is None  # only one image
        picture_url = img["src"]
        print(f"Found user profile picture at '{picture_url}'.")
        # no break to check if only one

    if not picture_url:
        raise RuntimeError("User profile picture not found")

    return picture_url


def write_seller_profile_url_in_file(url: str, output_dir: Path) -> None:
    (output_dir / "profile_picture_url").write_text(url)


def download_and_save_profile_picture(url: str, output_dir: Path) -> None:
    data = download(url)
    save(data, output_dir / "profile_picture.jpg")


def parse_args() -> Namespace:
    parser = argparse.ArgumentParser(prog="download_vinted")

    parser.add_argument("url", default="", help="url or file")
    parser.add_argument(
        "-d", dest="outdpath", required=False, default="output", help="output directory"
    )
    parser.add_argument(
        "--driver",
        dest="driver",
        required=False,
        default="geckodriver",
        help="driver for selenium, default 'geckodriver'",
    )
    parser.add_argument(
        "--executable",
        dest="executable",
        required=False,
        default=None,
        help="executable of firefox",
    )
    parser.add_argument(
        "--source",
        dest="source",
        required=False,
        default=None,
        help="source of the main page html",
    )
    args = parser.parse_args()

    return args


def main() -> None:
    args = parse_args()
    go(
        url=args.url,
        dest_dir=Path(args.outdpath),
        driver=args.driver,
        source=Path(args.source) if args.source else None,
        executable=args.executable,
    )


if __name__ == "__main__":
    main()
