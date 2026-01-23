# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Django admin (built-in)
    path('admin/', admin.site.urls),
    
    # User authentication and management endpoints
    # These go under /api/ (from users.urls)
    path('api/', include('users.urls')),
    path('api/reports/', include('reports.urls')),
    # Student management endpoints
    # These also go under /api/ (from students.urls)
    path('api/', include('students.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)