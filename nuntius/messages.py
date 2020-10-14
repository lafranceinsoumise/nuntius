import re
from itertools import count
from urllib.parse import quote as url_quote

from django.core.mail import EmailMultiAlternatives, EmailMessage
from django.template import Context
from django.urls import reverse

from nuntius import app_settings
from nuntius.utils.messages import sign_url, extend_query

RE_URL = re.compile(
    r"(?P<prefix><a[^>]* href\s*=[\s\"']*)(?P<url>http[^\"'>\s]+)",
    flags=re.MULTILINE | re.IGNORECASE,
)


def insert_tracking_image_template(html_message):
    # use old style formatting to avoid ugly escaping of template variable
    img_url = "%s%sopen/{{ nuntius_tracking_id }}" % (
        app_settings.PUBLIC_URL,
        reverse("nuntius_mount_path"),
    )
    img = f'<img src="{img_url}" width="1" height="1" alt="nt">'
    return re.sub(
        r"(</body\b)", img + r"\1", html_message, flags=re.MULTILINE | re.IGNORECASE
    )


def make_tracking_url(url, campaign, tracking_id, link_index):
    url = extend_query(
        url,
        defaults={
            "utm_content": f"link-{link_index}",
            "utm_term": getattr(campaign.segment, "utm_term", ""),
        },
    )

    relative_url = reverse(
        "nuntius_track_click",
        kwargs={
            "tracking_id": tracking_id,
            "signature": sign_url(campaign, url),
            "link": url_quote(url, safe=""),
        },
    )
    return f"{app_settings.PUBLIC_URL}{relative_url}"


def href_url_replacer(campaign, tracking_id):
    link_counter = count()

    def url_replace(match):
        url = make_tracking_url(
            match.group("url"), campaign, tracking_id, next(link_counter)
        )
        return f"{match.group('prefix')}{url}"

    return url_replace


def add_tracking_information(html_body: str, campaign, tracking_id):
    return RE_URL.sub(
        href_url_replacer(campaign=campaign, tracking_id=tracking_id), html_body
    )


def message_for_event(sent_event):
    """Generate an email message corresponding to a CampaignSentEvent instance

    :param sent_event: the CampaignSentEvent instance associating a campaign and a subscriber for which the
        message should be generated
    :type sent_event: class:`nuntius.models.CampaignSentEvent`
    :return: a complete email message, for the campaign, with the subscriber information interpolated
    :rtype: class:`django.core.mail.message.EmailMessage`
    """
    subscriber = sent_event.subscriber
    campaign = sent_event.campaign
    email = sent_event.email

    subscriber_data = Context(
        {
            "nuntius_tracking_id": sent_event.tracking_id,
            **subscriber.get_subscriber_data(),
        }
    )

    html_body = add_tracking_information(
        campaign.html_template.render(context=subscriber_data),
        campaign,
        sent_event.tracking_id,
    )
    text_body = campaign.text_template.render(context=subscriber_data)

    message_class = (
        EmailMultiAlternatives if (text_body and html_body) else EmailMessage
    )

    message = message_class(
        subject=campaign.message_subject,
        body=text_body or html_body,
        from_email=campaign.from_header,
        to=[email],
        reply_to=[campaign.reply_to_header]
        if campaign.reply_to_header is not None
        else None,
    )

    if text_body and html_body:
        message.attach_alternative(html_body, "text/html")
    elif html_body:
        message.content_subtype = "html"

    return message
