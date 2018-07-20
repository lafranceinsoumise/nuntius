from django.urls import path

from mailer.views import MosaicoImageProcessorView

urlpatterns = [
    path('img/', MosaicoImageProcessorView.as_view(), name='mailer_mosaico_image_processor'),
]
