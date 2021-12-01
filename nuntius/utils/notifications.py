from urllib.parse import quote as url_quote

from django.urls import reverse

from nuntius import app_settings
from nuntius.models import PushCampaignSentStatusType
from nuntius.utils.messages import sign_url, extend_query


def get_pushing_error_classes():
    try:
        from push_notifications import apns, gcm
    except ImportError:
        classes = tuple()
    else:
        classes = (gcm.GCMError, apns.APNSError)

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


def push_apns_notification(device, notification, thread_id):
    try:
        from push_notifications.apns import APNSServerError
    except ImportError as e:
        raise e
    else:
        try:
            device.send_message(
                message=notification,
                thread_id=thread_id,
                extra={"url": notification["url"]},
            )
        except APNSServerError as e:
            if "Unregistered" in str(e):
                device.active = False
                device.save()
            raise e


def push_gcm_notification(device, notification, thread_id):
    device.send_message(message=None, thread_id=thread_id, extra=notification)


def push_notification(notification, push_sent_event):
    try:
        from push_notifications.models import APNSDevice, GCMDevice
    except ImportError:
        push_sent_event.result = PushCampaignSentStatusType.ERROR
    else:
        push_sent_event.result = PushCampaignSentStatusType.PENDING

        pushed_count = 0
        for device in push_sent_event.devices:
            try:
                if isinstance(device, APNSDevice):
                    push_apns_notification(
                        device, notification, push_sent_event.campaign.id
                    )
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
