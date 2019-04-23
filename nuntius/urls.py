from django.urls import path

from nuntius.views import mosaico_image_processor_view

urlpatterns = [
    path("img/", mosaico_image_processor_view, name="nuntius_mosaico_image_processor")
]
