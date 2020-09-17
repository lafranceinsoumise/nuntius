import hashlib
import hmac
from base64 import urlsafe_b64encode
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import html2text
from PIL import Image, ImageDraw

from nuntius import app_settings

_h = html2text.HTML2Text()
_h.ignore_images = True

DIGEST_MOD = hashlib.sha1


def generate_plain_text(html_message):
    return _h.handle(html_message)


def generate_placeholder(width, height):
    image = Image.new("RGB", (int(width), int(height)), "#707070")
    draw = ImageDraw.Draw(image)

    x = 0
    y = 0
    line_size = 40
    while y < height:
        draw.polygon(
            [
                (x, y),
                (x + line_size, y),
                (x + line_size * 2, y + line_size),
                (x + line_size * 2, y + line_size * 2),
            ],
            fill="#808080",
        )
        draw.polygon(
            [
                (x, y + line_size),
                (x + line_size, y + line_size * 2),
                (x, y + line_size * 2),
            ],
            fill="#808080",
        )
        x = x + line_size * 2
        if x > width:
            x = 0
            y = y + line_size * 2

    (textwidth, textheight) = draw.textsize(f"{width} x {height}")
    draw.text(
        ((int(width) - textwidth) / 2, (int(height) - textheight) / 2),
        f"{width} x {height}",
        (255, 255, 255),
    )

    return image


def build_absolute_uri(request, location):
    if app_settings.PUBLIC_URL:
        return app_settings.PUBLIC_URL + location
    return request.build_absolute_uri(location)


def sign_url(campaign, url):
    return str(
        urlsafe_b64encode(
            hmac.new(bytes(campaign.signature_key), url.encode(), DIGEST_MOD).digest()
        ).decode()
    )


def url_signature_is_valid(campaign, url, signature):
    expected = sign_url(campaign, url)
    if len(expected) != len(signature):
        return False
    return hmac.compare_digest(expected, signature)


def extend_query(url, defaults=None, replace=None):
    url_parts = list(urlparse(url))
    query = parse_qs(url_parts[4])

    if defaults is not None:
        for key, value in defaults.items():
            query.setdefault(key, value)

    if replace is not None:
        query.update(**replace)

    url_parts[4] = urlencode(query, doseq=True)
    return urlunparse(url_parts)
