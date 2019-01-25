from urllib.parse import urlparse

from PIL import Image
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.http.request import validate_host
from django.views.generic import DetailView

from nuntius.models import MosaicoImage
from nuntius.utils import generate_placeholder


class MosaicoImageProcessorView(DetailView):
    def get(self, *args, **kwargs):
        if self.request.GET.get("method") == "placeholder":
            (width, height) = self.request.GET.get("params").split(",")
            image = generate_placeholder(int(width), int(height))
            response = HttpResponse(content_type="image/png")
            image.save(response, "PNG")
            return response

        if self.request.GET.get("src"):
            src = self.request.GET.get("src")
            host = urlparse(src).netloc.split(":")[0]
            allowed_hosts = settings.ALLOWED_HOSTS
            if settings.DEBUG and not allowed_hosts:
                allowed_hosts = ["localhost", "127.0.0.1", "[::1]"]
            if not validate_host(host, allowed_hosts):
                return HttpResponseBadRequest()

            (width, height) = self.request.GET.get("params").split(",")
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
