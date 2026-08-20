from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.generic import RedirectView
from django.views.static import serve as static_serve
from pathlib import Path

urlpatterns = [
    path('admin/', admin.site.urls),

    # API routes
    path('api/monitoring/', include('monitoring.urls')),
    path('api/users/', include('users.urls')),
    path('api/auth/', include('users.urls')),
    path('api/logs/', include('logs.urls')),

    # Web UI (serve existing frontend files)
    path('', RedirectView.as_view(url='/app/user_login.html', permanent=False), name='home'),
    path('app/<path:path>', static_serve, {
        'document_root': str(Path(settings.BASE_DIR) / 'frontend')
    }),
]