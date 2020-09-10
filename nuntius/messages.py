import re
from itertools import count
from smtplib import SMTPServerDisconnected, SMTPRecipientsRefused
from time import sleep
from urllib.parse import quote as url_quote

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template import Template, Context
from django.urls import reverse
from django.utils import timezone

from nuntius.models import (
    Campaign,
    CampaignSentEvent,
    CampaignSentStatusType,
    AbstractSubscriber,
)
from nuntius.utils import sign_url, extend_query

try:
    from anymail.exceptions import AnymailRecipientsRefused
except:

    class AnymailRecipientsRefused(BaseException):
        pass


def replace_url(url, campaign, tracking_id, link_index, public_url):
    url = extend_query(
        url,
        defaults={
            "utm_content": link_index,
            "utm_term": getattr(campaign.segment, "utm_term", ""),
        },
    )

    return public_url + reverse(
        "nuntius_track_click",
        kwargs={
            "tracking_id": tracking_id,
            "signature": sign_url(campaign, url),
            "link": url_quote(url, safe=""),
        },
    )


def replace_vars(campaign, data, public_url):
    context = Context(data)

    html_rendered_content = Template(campaign.message_content_html).render(
        context=context
    )

    link_counter = count()
    html_rendered_content = re.sub(
        r"(<a[^>]* href\s*=[\s\"']*)(http[^\"'>\s]+)",
        lambda match: match.group(1)
        + replace_url(
            url=match.group(2),
            campaign=campaign,
            tracking_id=data["nuntius_tracking_id"],
            link_index=f"link-{next(link_counter)}",
            public_url=public_url,
        ),
        html_rendered_content,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    text_rendered_content = Template(campaign.message_content_text).render(
        context=context
    )

    return text_rendered_content, html_rendered_content


def reset_connection(connection):
    try:
        connection.close()
    except Exception:
        pass

    for retry in reversed(range(1, 11)):
        try:
            sleep(1 / retry)
            connection.open()
        except Exception:
            connection.close()
        else:
            break


def insert_tracking_image(public_url, html_message):
    img_url = (
        public_url + reverse("nuntius_mount_path") + "open/{{ nuntius_tracking_id }}"
    )
    img = '<img src="{}" width="1" height="1" alt="nt">'.format(img_url)
    return re.sub(
        r"(<\/body\b)", img + r"\1", html_message, flags=re.MULTILINE | re.IGNORECASE
    )
