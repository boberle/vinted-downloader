# Vinted Product Downloader

Vinted is a website to buy and sell second-hand clothes available in several countries in Europe.  Sometimes it's useful to download the photographs of an article, for example if you buy a product that you want to later resell on the platform and you don't want to take the photographs again.

At the time of writing (August the 6th, 2023), scrapping information from the Vinted website is really easy (it used to be a lot harder).  You can find all the details below. It is so easy that you can download all the photographs in full size with one command line, without even needing python or any programming language.

But if you want more information (not just the photographs) or don't know how to pipe commands on the command line, here is a python script that will:

- download and extract the details about a Vinted product. This json contains all the information available for the product, the user, the photographs, etc.
- download all the photographs of the product in full resolution
- download the profile picture of the seller (with the `--seller` option)

It is working like this:

```bash
python3 vinted_downloader.py "PRODUCT_URL"
# or, to also download the seller profile:
python3 vinted_downloader.py --seller "PRODUCT_URL"
```

Then you get the following files:

- `item.json`: all the information you want and you don't want
- `item_summary`: main information (url, title, description, etc.)
- `photo_01.jpg`: all the photos for the item
- `seller.jpg`: with the `--seller` option


## How does it work?

First download the raw html found at the product url, for example `https://www.vinted.fr/CATEGORY/SUBCATEGORY/.../PRODUCT_ID-SLUG`

By reading the code, you will find interesting json document inside `<script type="application/json" class="js-react-on-rails-component" data-component-name="NAME">` tags.

The name `NAME` of these tags are things like `Header`, `Advertisement`, `ItemPhotoGrid`, `InfoBanner`... We are interested in `ItemDetails` (which contains the json contained in `ItemPhotoGrid`, `ItemDescription` and `ItemUserInfo`).

So we just use `BeautifulSoup` to extract to find and extract the tag `<script type="application/json" class="js-react-on-rails-component" data-component-name="ItemDetails">`, and read the json inside.

The interesting parts of the json are the following ones (using `jq` format):

```
cat itemdetails.json | jq ".item.title"
cat itemdetails.json | jq ".item.description"
cat itemdetails.json | jq ".item.photos[] | .full_size_url"
cat itemdetails.json | jq ".item.user.login"
cat itemdetails.json | jq ".item.user.last_logged_on_ts"
cat itemdetails.json | jq ".item.user.photo.full_size_url"
```

But you can find a lot more information in the json (the price, if the item is reserved, hidden, etc.), really everything that is displayed on the page, and even more.

So, if you want to download the photos in the original size using only the command line (I'm assuming you are using Linux or Mac, if you made it so far):

```bash
curl "https://PRODUCT_URL" | perl -ne 'm/(?<=data-component-name="ItemDetails").+?(\{.+?\})(?=<\/script>)/ && print "$1"' | jq -r ".item.photos[] | .full_size_url" | xargs wget
```

Explanation:

- `curl` will download the html
- `perl` wil extract the json by look at the correct tag in the html code
- `jq` will extract the photo urls (full size)
- `wget` will download all the photos


## Version

This is version 2. Not back compatible with version 1.