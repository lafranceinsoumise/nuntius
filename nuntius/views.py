from base64 import b64decode
from urllib.parse import urlparse, parse_qs

from PIL import Image
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import F
from django.http import HttpResponse, HttpResponseBadRequest, Http404
from django.http.request import validate_host
from django.shortcuts import redirect, get_object_or_404

from nuntius.models import MosaicoImage, CampaignSentEvent
from nuntius.utils import generate_placeholder, url_signature_is_valid


def mosaico_image_processor_view(request):
    params = request.GET.get("params", "").split(",")

    if len(params) != 2:
        return HttpResponseBadRequest()

    (width, height) = (
        int(params[0].replace("null", "0")),
        int(params[1].replace("null", "0")),
    )

    if request.GET.get("method") == "placeholder" and width and height:
        image = generate_placeholder(width, height)
        response = HttpResponse(content_type="image/png")
        image.save(response, "PNG")
        return response

    if request.GET.get("src") and (width or height):
        src = request.GET.get("src")
        host = urlparse(src).netloc.split(":")[0]
        allowed_hosts = settings.ALLOWED_HOSTS
        if settings.DEBUG and not allowed_hosts:
            allowed_hosts = ["localhost", "127.0.0.1", "[::1]"]
        if not validate_host(host, allowed_hosts):
            return HttpResponseBadRequest()

        image = MosaicoImage.objects.get(
            file=urlparse(src).path.replace(settings.MEDIA_URL, "", 1)
        )
        image = Image.open(image.file.path)

        if width and height:
            ratio = min(width / image.size[0], height / image.size[1])
        elif width:
            ratio = width / image.size[0]
        elif height:
            ratio = height / image.size[1]

        image.resize((round(size * ratio) for size in image.size), Image.ANTIALIAS)
        response = HttpResponse(content_type=f"image/{image.format.lower()}")
        image.save(response, image.format)
        return response

    return HttpResponseBadRequest()


def track_open_view(request, tracking_id):
    CampaignSentEvent.objects.filter(tracking_id=tracking_id).update(
        open_count=F("open_count") + 1
    )
    return HttpResponse(
        b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        ),
        content_type="image/png",
    )


def track_click_view(request, tracking_id, link, signature):
    campaign_sent_event = get_object_or_404(CampaignSentEvent, tracking_id=tracking_id)

    CampaignSentEvent.objects.filter(tracking_id=tracking_id).update(
        click_count=F("click_count") + 1
    )

    url = parse_qs("link=" + link).get("link")

    if url is None or len(url) != 1:
        raise

    if not url_signature_is_valid(campaign_sent_event.campaign, url[0], signature):
        raise PermissionDenied()

    return redirect(url[0])
