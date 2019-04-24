from base64 import b64decode
from urllib.parse import urlparse

from PIL import Image
from django.conf import settings
from django.db.models import F
from django.http import HttpResponse, HttpResponseBadRequest
from django.http.request import validate_host

from nuntius.models import MosaicoImage, CampaignSentEvent
from nuntius.utils import generate_placeholder


def mosaico_image_processor_view(request):
    if request.GET.get("method") == "placeholder":
        (width, height) = request.GET.get("params").split(",")
        image = generate_placeholder(int(width), int(height))
        response = HttpResponse(content_type="image/png")
        image.save(response, "PNG")
        return response

    if request.GET.get("src"):
        src = request.GET.get("src")
        host = urlparse(src).netloc.split(":")[0]
        allowed_hosts = settings.ALLOWED_HOSTS
        if settings.DEBUG and not allowed_hosts:
            allowed_hosts = ["localhost", "127.0.0.1", "[::1]"]
        if not validate_host(host, allowed_hosts):
            return HttpResponseBadRequest()

        (width, height) = request.GET.get("params").split(",")
        (width, height) = (
            int(width.replace("null", "0")),
            int(height.replace("null", "0")),
        )
        image = MosaicoImage.objects.get(
            file=urlparse(src).path.replace(settings.MEDIA_URL, "", 1)
        )
        image = Image.open(image.file.path)

        if width and not height:
            ratio = width / image.size[0]
        if height and not width:
            ratio = height / image.size[1]
        if width and height:
            ratio = min(width / image.size[0], height / image.size[1])

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
