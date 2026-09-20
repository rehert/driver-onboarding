"""
URL configuration for driver_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
from onboarding import views as onboarding_views
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# ============================================================
# 1. IMPORTS
# ============================================================

from django.contrib import admin
from django.urls import include, path
from onboarding import views as onboarding_views


# ============================================================
# 2. MAIN PROJECT URLS
# ============================================================

urlpatterns = [

    # Django management interface
    path(
        "admin/",
        admin.site.urls,
    ),

    # Driver website
    path("", include("onboarding.urls")),
    path("media/<path:file_path>", onboarding_views.protected_media, name="protected_media"),
]



