"""newsletter URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.views.generic import RedirectView

from nuntius import urls as nuntius_urls
from standalone.admin import admin_site

from . import views

urlpatterns = [
    path("", RedirectView.as_view(url="admin/")),
    path("admin/", admin_site.urls),
    path("nuntius/", include(nuntius_urls)),
    path('envoyer-notification/', views.envoyer_notification_push, name='envoyer_notification_push'),
    path("anymail/", include("anymail.urls")),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
