from pathlib import Path

import pytest

from vinted_downloader import Details, load_html


@pytest.fixture
def testdata_dir() -> Path:
    return Path(__file__).parent / "testdata"


@pytest.fixture
def html_data_1(testdata_dir: Path) -> str:
    return load_html(testdata_dir / "20230806_multiple_images.html")


def test_found_details(html_data_1: str) -> None:
    details = Details(html_data_1)
    assert details.json["item"]["title"] == "Bruidtop 'Blanca', croptop maat S/M (38)"

    assert details.title == "Bruidtop 'Blanca', croptop maat S/M (38)"
    assert (
        details.description
        == "Ongedragen bruidstopje! Voor een tweedelige jurk (rok en top). Ik had meerdere topjes, deze uiteindelijk niet gedragen. Mooi kant, kwalitatieve stof, van bruidsmodewinkel: Labude in Köln. Nieuwprijs is 650eu. Kleur: ivoor."
    )
    assert details.seller == "someuser"
    assert details.seller_id == 123456
    assert details.seller_last_logged_in == "2023-08-05T19:32:19+02:00"
    assert (
        details.seller_photo_url
        == "https://images1.vinted.net/tc/03_00220_MTRW4DpP4QqthgPid4asMuah/1648879549.jpeg?s=b5bbb35fc60ec9c9bca454f56a8a78d8aeadac82"
    )
    assert details.full_size_photo_urls == [
        "https://images1.vinted.net/tc/01_0001a_aT7WiZ1BdMeoiyTKEXnBBV8i/1688230835.jpeg?s=9866ce62e4d4e49115c7e8b770ee2fd8470a96cc",
        "https://images1.vinted.net/tc/03_023eb_aR7PJvsJnwjPrm16sdDBiDh5/1688230835.jpeg?s=2e7f7298ba80b680583dc141b2d4736e82df620a",
        "https://images1.vinted.net/tc/03_01fe7_mKeKP3msFbxHdRtDT3jpoBNj/1688230835.jpeg?s=d3df16ce2e83d323500c3874067d626537a45b2a",
        "https://images1.vinted.net/tc/01_0239e_hxvrRBZPwEDgf71RW7Dpu18z/1688276801.jpeg?s=52bffcd2a7209014acd704a895e0ec14642d8a5d",
        "https://images1.vinted.net/tc/03_00a03_gMhNMqSTzxhQhmn8CBPeCYfC/1688276801.jpeg?s=752cd97cfa1e9102149605f17a5efbf4fc6b32cb",
        "https://images1.vinted.net/tc/03_02533_SVYnFdcJRxxLWJPwvVvJfK2m/1688276801.jpeg?s=89dbb9a3e2a09175c4be3bbc3b610f8a2b90d95d",
        "https://images1.vinted.net/tc/02_00f95_mmY9RQwhw6znYJfUrx4Qxt8f/1688276801.jpeg?s=8fac9301bb65c4afd033c3be7bb972cfc959fff9",
    ]
