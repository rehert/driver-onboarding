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
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# ============================================================
# 1. IMPORTS
# ============================================================

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


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
    path(
        "",
        include("onboarding.urls"),
    ),
]


# ============================================================
# 3. LOCAL MEDIA FILES

# Only used while DEBUG=True.
# ============================================================

if settings.DEBUG:

    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )

