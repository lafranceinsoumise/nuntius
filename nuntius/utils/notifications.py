from urllib.parse import quote as url_quote

from django.urls import reverse

from nuntius import app_settings
from nuntius.models import PushCampaignSentStatusType
from nuntius.utils.messages import sign_url, extend_query

from firebase_admin import messaging

def get_pushing_error_classes():
    try:
        from push_notifications import gcm
    except ImportError:
        classes = tuple()
    else:
        classes = (gcm.FirebaseError)

    return classes


def make_tracking_url(url, campaign, tracking_id):
    url = extend_query(
        url, defaults={"utm_term": getattr(campaign.segment, "utm_term", "")}
    )

    relative_url = reverse(
        "nuntius_track_push_click",
        kwargs={
            "tracking_id": tracking_id,
            "signature": sign_url(campaign, url),
            "link": url_quote(url, safe=""),
        },
    )
    return f"{app_settings.LINKS_URL}{relative_url}"


def notification_for_event(sent_event):
    """Generate a push notification payload corresponding to a PushCampaignSentEvent instance

    :param sent_event: the PushCampaignSentEvent instance associating a campaign and a subscriber for which the
        notification should be generated
    :type sent_event: class:`nuntius.models.PushCampaignSentEvent`
    :return: a dictionnary describing the push notification content
    :rtype: dict`
    """

    # subscriber = sent_event.subscriber
    campaign = sent_event.campaign
    notification_url = make_tracking_url(
        campaign.notification_url, campaign, tracking_id=sent_event.tracking_id
    )
    notification = {
        "title": campaign.notification_title,
        "url": notification_url,
        "body": campaign.notification_body,
        "tag": campaign.notification_tag,
        "icon": campaign.notification_icon,
    }

    return notification

def push_gcm_notification(device, notification, thread_id):
    ttl = 259200 # equals 3 days
    push_message = messaging.Message(
        data={
            "url": notification["url"]
        },
        notification=messaging.Notification(
            title=notification["title"],
            body=notification["body"],
            image=notification["notification_icon"]
        ),
        android=messaging.AndroidConfig(
            ttl=ttl,
            collapse_key=thread_id
        ),
        apns=messaging.APNSConfig(
            headers={
                "apns-expiration": ttl,
                "apns-collapse-id": thread_id
            }
        )
    )
    device.send_message(push_message)


def push_notification(notification, push_sent_event):
    try:
        from push_notifications.models import GCMDevice
    except ImportError:
        push_sent_event.result = PushCampaignSentStatusType.ERROR
    else:
        push_sent_event.result = PushCampaignSentStatusType.PENDING

        pushed_count = 0
        for device in push_sent_event.devices:
            try:
                if isinstance(device, GCMDevice):
                    push_gcm_notification(
                        device, notification, push_sent_event.campaign.id
                    )
            except Exception:
                pass
            else:
                pushed_count += 1

        if pushed_count > 0:
            push_sent_event.result = PushCampaignSentStatusType.OK
        else:
            push_sent_event.result = PushCampaignSentStatusType.ERROR

    push_sent_event.save()
