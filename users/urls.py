# users/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from .views import (
    # Session auth
    admin_login, admin_logout, get_csrf_token, check_auth, get_current_user,
    
    # JWT auth
    CustomTokenObtainPairView,
    
    # Public endpoints
    register_user, update_profile, change_password, public_profile, public_login,
    
    # User management
    UserViewSet,
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')


urlpatterns = [
    # Session authentication (for React admin)
    path('auth/admin/login/', admin_login, name='admin_login'),
    path('auth/admin/logout/', admin_logout, name='admin_logout'),
    path('auth/csrf/', get_csrf_token, name='get_crf_token'),
    path('auth/check/', check_auth, name='check_auth'),
    path('auth/current-user/', get_current_user, name='current_user'),


    
    # JWT authentication (for API clients)
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # Public endpoints
    path('auth/register/', register_user, name='register_user'),
    path('auth/public/login/', public_login, name='public_login'),
    path('auth/public/profile/', public_profile, name='public_profile'),
    
    # Profile management
    path('auth/update-profile/', update_profile, name='update_profile'),
    path('auth/change-password/', change_password, name='change_password'),
    
    # User management (admin only)
    path('', include(router.urls)),
    
]
