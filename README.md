# Vinted Product Downloader

Vinted is a website to buy and sell second-hand clothes available in several countries in Europe.  Sometimes it's useful to download the photographs of an article, for example if you buy a product that you want later resell on the platform and you don't want take the photographs again.

This script will download the product page, the associated photographs, and some information about the seller, including their profile picture.

You will need the `geckodriver` to download the seller profile picture:

- download the lastest version from [github](https://github.com/mozilla/geckodriver/releases)
- extract the binary from tarball
- copy it to `/tmp`

Adapt the script if you want to do things differently.

Then run the script:

```
python3 vinted_downloader.py URL_OF_THE_PRODUCT
```

