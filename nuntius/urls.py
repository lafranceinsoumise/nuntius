from django.urls import path

from nuntius.views import MosaicoImageProcessorView

urlpatterns = [
    path(
        "img/",
        MosaicoImageProcessorView.as_view(),
        name="nuntius_mosaico_image_processor",
    )
]
