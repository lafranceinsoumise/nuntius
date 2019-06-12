from django.urls import path, reverse_lazy
from django.views.generic import RedirectView

from nuntius.views import (
    mosaico_image_processor_view,
    track_open_view,
    track_click_view,
)

urlpatterns = [
    path(
        "",
        RedirectView.as_view(url=reverse_lazy("admin:nuntius")),
        name="nuntius_mount_path",
    ),
    path("img/", mosaico_image_processor_view, name="nuntius_mosaico_image_processor"),
    path("open/<str:tracking_id>", track_open_view, name="nuntius_track_open"),
    path(
        "link/<str:tracking_id>/<str:link>/<str:signature>",
        track_click_view,
        name="nuntius_track_click",
    ),
]
