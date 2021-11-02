import time
import os
import random
import re
import json
import argparse

from urllib.parse import urlparse
import urllib.request
import urllib
from selenium import webdriver

from bs4 import BeautifulSoup

SNAP = (1, 2, 3, 4,)
#SNAP = (6, 7, 8)
#SNAP = ()


def download(url):
    if len(SNAP):
        print("(zzzzzzz...)")
        time.sleep(random.choice(SNAP))
    try:
        print("Downloading from `%s'" % url)
        fh = urllib.request.urlopen(url)
        return fh.read()
    except urllib.error.URLError:
        print("*** can't read the page `%s' ***" % url)
        #input("Press Enter to continue...")
        raise


def save(data, dpath, fname, *, binary=True):
    fpath = os.path.join(dpath, fname)
    print(f"Saving '{fpath}'.")
    open(fpath, 'wb' if binary else 'w').write(data)



def get_profile_picture_url(soup):
    image_url = None
    for script in soup.find_all('script', {'data-component-name': "Profile"}):
        data = json.loads(script.string)
        assert image_url is None # only one
        photo_data = data['userInfoProps']['user']['photo']
        if photo_data is not None:
            image_url = photo_data['url']
            print(f"Found user profile picture at '{image_url}'.")
        # no break to check if only one
    return image_url

def ask_to_save_seller_page_and_picture(url, dpath):
    seller_dom = os.path.abspath(os.path.join(dpath, 'seller_dom.html'))
    print(f"Go to {url} and save the DOM to {seller_dom}")
    seller_photo = os.path.abspath(os.path.join(dpath, 'profile.jpg'))
    print(f"Also, save the picture, if any, to {seller_photo}")
    input("Press Enter when done.")


def get_seller_dom_and_picture_url(url, dpath):
    # dom
    driver = webdriver.Firefox(executable_path="/tmp/geckodriver")
    driver.get(url)
    time.sleep(2)
    html = driver.execute_script("return document.body.outerHTML;")
    with open(os.path.join(dpath, 'seller_dom.html'), "w") as f:
        f.write(html)
    driver.close()
    # image
    soup = BeautifulSoup(html, "lxml")
    image_url = None
    for img in soup.find_all('img'):
        if '/f800/' not in img['src']:
            continue
        assert image_url is None # only one
        image_url = img['src']
        print(f"Found user profile picture at '{image_url}'.")
        # no break to check if only one
    if not image_url:
        raise RuntimeError("User profile picture not found")
    return image_url




def download_and_save(url, outdpath):

    url = url.rstrip("/")
    parsed = urlparse(url)
    #input(parsed)

    # dest dir
    dname = os.path.basename(parsed.path)
    #input(dname)
    assert dname
    dpath = os.path.join(outdpath, dname)
    if os.path.exists(dpath):
        raise FileExistsError(dpath)
    os.makedirs(dpath)

    open(os.path.join(dpath, 'url'), 'w').write(url)

    # main page
    main_page = download(url).decode('utf-8')
    save(main_page, dpath, 'page.html', binary=False)

    # item images
    soup = BeautifulSoup(main_page, "lxml")
    div = soup.find("div", class_="item-photos")
    image_urls = []
    for figure in div.find_all('figure'):
        image_url = figure.a['href']
        print("Found an image at '%s'" % image_url)
        image_urls.append(image_url)

    # some supplementary images (only the first 5 are shown on the main
    # page) are in a "u-hidden" div (there are several of this kind of div, we
    # want the one with the 'item-description' figures)
    for u_hidden_div in soup.find_all("div", class_="u-hidden"):
        for figure in u_hidden_div.find_all('figure', class_="item-description"):
            image_url = figure.a['href']
            print("Found a supplementary image at '%s'" % image_url)
            image_urls.append(image_url)

    assert image_urls

    open(os.path.join(dpath, 'image_urls'), 'w').write("\n".join(image_urls))

    for i, image_url in enumerate(image_urls):
        image_data = download(image_url)
        save(image_data, dpath, f"image_{i}.jpg", binary=True)

    # seller url
    #seller_url = soup.find('span', class_="user-login-name").a['href']
    seller_id = soup.find(
        'script',
        attrs={'data-component-name':"ItemUserInfo"},
    ).string;
    assert seller_id
    seller_id = json.loads(seller_id)['user']['id']
    seller_url = f"/members/{seller_id}"
    seller_url = f"{parsed.scheme}://{parsed.netloc}{seller_url}"
    #input(seller_url)

    open(os.path.join(dpath, 'seller_url'), 'w').write(seller_url)

    # seller page
    seller_page = download(seller_url).decode('utf-8')
    save(seller_page, dpath, 'seller.html', binary=False)

    # seller profile picture
    #soup = BeautifulSoup(seller_page, "lxml")
    #profile_picture_url = get_profile_picture_url(soup)
    profile_picture_url = get_seller_dom_and_picture_url(seller_url, dpath)
    if profile_picture_url is not None:
        open(os.path.join(dpath, 'profile_picture_url'), 'w').write(
            profile_picture_url)
        profile_picture_data = download(profile_picture_url)
        save(profile_picture_data, dpath, f"profile_picture.jpg", binary=True)



def parse_args():
    # definition
    parser = argparse.ArgumentParser(prog="progname",
        description="what the program does",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    # arguments (not options)
    #parser.add_argument("infpaths", nargs="+", help="input files")
    parser.add_argument("url", default="", help="url")
    #parser.add_argument("outfpath", default="", help="output file")
    # options
    #parser.add_argument("--swith", dest="switch", default=False,
    #   action="store_true", help="")
    parser.add_argument("-d", dest="outdpath", required=False,
        default="output", help="output directory")
    # reading
    args = parser.parse_args()
    return args



def main():
    args = parse_args()
    download_and_save(args.url, args.outdpath)


if __name__ == "__main__":
    main()



