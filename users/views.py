# users/views.py
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.middleware.csrf import get_token
from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
import json
import logging

from .models import User
from .serializers import (
    UserSerializer, UserUpdateSerializer, RegisterSerializer,
    LoginSerializer
)

logger = logging.getLogger(__name__)


# ==================== SIMPLE SESSION AUTHENTICATION VIEWS ====================

# users/views.py - Update the admin_login function
@csrf_exempt
@require_POST
def admin_login(request):
    """
    Admin login that accepts BOTH username and email
    """
    try:
        # Parse JSON data
        try:
            data = json.loads(request.body)
            logger.info(f"Login attempt: {data}")
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON format'
            }, status=400)
        
        # Get login identifier (can be username or email)
        login_identifier = data.get('username') or data.get('email')
        password = data.get('password', '').strip()
        
        if not login_identifier or not password:
            return JsonResponse({
                'success': False,
                'error': 'Username/Email and password are required'
            }, status=400)
        
        user = None
        
        # Check if it's an email or username
        if '@' in login_identifier:
            # It's an email - find user by email first
            try:
                logger.info(f"Looking for user by email: {login_identifier}")
                user_obj = User.objects.get(email=login_identifier)
                logger.info(f"Found user by email: {user_obj.username}, role: {user_obj.role}, is_staff: {user_obj.is_staff}")
                # Authenticate with username
                user = authenticate(request, username=user_obj.username, password=password)
                logger.info(f"Authentication result: {user}")
            except User.DoesNotExist:
                logger.error(f"No user found with email: {login_identifier}")
                user = None
        else:
            # It's a username - authenticate directly
            logger.info(f"Looking for user by username: {login_identifier}")
            user = authenticate(request, username=login_identifier, password=password)
            if user:
                logger.info(f"Found user by username: {user.username}, role: {user.role if hasattr(user, 'role') else 'N/A'}, is_staff: {user.is_staff}")
        
        if user is not None:
            # Check if user is active
            if not user.is_active:
                return JsonResponse({
                    'success': False,
                    'error': 'Account is inactive. Please contact administrator.'
                }, status=401)
            
            # Check if user has admin/committee/staff role
            allowed_roles = ['admin', 'committee', 'staff']
            
            # Get user's role (handle if role attribute doesn't exist)
            user_role = user.role if hasattr(user, 'role') else 'N/A'
            
            user_has_access = (
                user.is_staff or 
                user.is_superuser or 
                (hasattr(user, 'role') and user.role in allowed_roles)
            )
            
            logger.info(f"User access check - Username: {user.username}, Role: {user_role}, Is Staff: {user.is_staff}, Is Superuser: {user.is_superuser}, Has Access: {user_has_access}")
            
            if user_has_access:
                auth_login(request, user)
                logger.info(f"Login successful for user: {user.username}")
                
                return JsonResponse({
                    'success': True,
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'first_name': user.first_name or '',
                        'last_name': user.last_name or '',
                        'role': user_role,
                        'is_staff': user.is_staff,
                        'is_superuser': user.is_superuser,
                        'phone': user.phone or '',
                        'ward': user.ward or '',
                        'is_active': user.is_active,
                        'is_verified': user.is_verified if hasattr(user, 'is_verified') else False,
                    }
                })
            else:
                logger.warning(f"Access denied for user {user.username} - role: {user_role}, is_staff: {user.is_staff}")
                return JsonResponse({
                    'success': False,
                    'error': 'Access denied. Admin or committee privileges required.',
                    'details': {
                        'user_role': user_role,
                        'is_staff': user.is_staff,
                        'is_superuser': user.is_superuser,
                        'allowed_roles': allowed_roles
                    }
                }, status=403)
        else:
            # Authentication failed
            logger.warning(f"Authentication failed for identifier: {login_identifier}")
            
            # Check if user exists but password is wrong
            try:
                if '@' in login_identifier:
                    existing_user = User.objects.get(email=login_identifier)
                else:
                    existing_user = User.objects.get(username=login_identifier)
                    
                logger.warning(f"User exists but authentication failed: {existing_user.username}")
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid password. Please check your password.',
                    'hint': 'User exists but password is incorrect'
                }, status=401)
            except User.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid username/email. User not found.',
                    'hint': 'Try registering or use a different username/email'
                }, status=401)
            
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'An error occurred during login: {str(e)}'
        }, status=500)

@csrf_exempt
@require_POST
def admin_logout(request):
    """
    Admin logout endpoint
    """
    try:
        auth_logout(request)
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_csrf_token(request):
    """
    Get CSRF token for React frontend
    """
    return JsonResponse({'csrfToken': get_token(request)})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_auth(request):
    """
    Check if user is authenticated and has admin privileges
    """
    user = request.user
    allowed_roles = ['admin', 'committee', 'staff']
    is_admin = (user.is_staff or user.is_superuser or 
                (hasattr(user, 'role') and user.role in allowed_roles))
    
    return Response({
        'authenticated': True,
        'is_admin': is_admin,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'role': user.role if hasattr(user, 'role') else 'staff',
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'phone': user.phone or '',
            'ward': user.ward or '',
        }
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    """
    Get current user details
    """
    user = request.user
    serializer = UserSerializer(user)
    return Response(serializer.data)

# ==================== JWT AUTHENTICATION VIEWS ====================

class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom JWT token obtain view that accepts BOTH email and username.
    Ensures that whatever key the frontend uses ('email' or 'username'), 
    the backend correctly maps it to the USERNAME_FIELD ('email').
    """
    def post(self, request, *args, **kwargs):
        # 1. Extract identifier from any possible key
        identifier = (
            request.data.get('email') or 
            request.data.get('username') or 
            request.data.get('identifier')
        )
        
        if identifier:
            # 2. If it's NOT an email (no '@'), try to find the user by username
            if '@' not in identifier:
                try:
                    user = User.objects.get(username=identifier)
                    # Use their actual email for authentication since USERNAME_FIELD is 'email'
                    request.data['email'] = user.email
                    request.data['username'] = user.email # Also set 'username' just in case serializer uses it
                except User.DoesNotExist:
                    # If user not found by username, it might still be an email without '@' 
                    # (unlikely but possible) or a wrong username.
                    # We ensure 'email' key exists to avoid 400 'This field is required'
                    request.data['email'] = identifier
            else:
                # 3. It's an email, ensure it's in both 'email' and 'username' keys
                request.data['email'] = identifier
                request.data['username'] = identifier
        
        return super().post(request, *args, **kwargs)

@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    """
    Public user registration
    """
    try:
        serializer = RegisterSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            
            # Set default values for new users
            user.role = 'public'  # All new users are public by default
            user.is_verified = False  # Requires admin verification
            user.save()
            
            # Generate JWT tokens for immediate login
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'success': True,
                'message': 'User registered successfully.',
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
                'user': UserSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return Response({
            'success': False,
            'error': 'An error occurred during registration'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== USER PROFILE VIEWS ====================

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """
    Update current user's profile
    """
    user = request.user
    serializer = UserUpdateSerializer(user, data=request.data, partial=True)
    
    if serializer.is_valid():
        serializer.save()
        return Response({
            'success': True,
            'message': 'Profile updated successfully.',
            'user': serializer.data
        })
    
    return Response({
        'success': False,
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    Change current user's password
    """
    user = request.user
    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')
    confirm_password = request.data.get('confirm_password')
    
    # Validate input
    if not old_password or not new_password or not confirm_password:
        return Response({
            'success': False,
            'error': 'All fields are required.'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if new_password != confirm_password:
        return Response({
            'success': False,
            'error': 'New passwords do not match.'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check old password
    if not user.check_password(old_password):
        return Response({
            'success': False,
            'error': 'Current password is incorrect.'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate new password
    try:
        from django.contrib.auth.password_validation import validate_password
        validate_password(new_password, user)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Set new password
    user.set_password(new_password)
    user.save()
    
    return Response({
        'success': True,
        'message': 'Password changed successfully.'
    })

# ==================== USER MANAGEMENT VIEWSET ====================

class IsAdminOrStaff(permissions.BasePermission):
    """
    Permission class for admin and staff users
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Admin, committee, and staff can access
        allowed_roles = ['admin', 'committee', 'staff']
        return (
            request.user.is_staff or 
            request.user.is_superuser or 
            (hasattr(request.user, 'role') and request.user.role in allowed_roles)
        )

class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing users (Admin only)
    """
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsAdminOrStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'ward']
    ordering_fields = ['username', 'email', 'date_joined', 'last_login']
    ordering = ['-date_joined']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return RegisterSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer
    
    def get_permissions(self):
        # Only superusers can delete users
        if self.action == 'destroy':
            self.permission_classes = [IsAuthenticated, permissions.IsAdminUser]
        return super().get_permissions()
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # If user is not superuser, don't show superusers
        if not self.request.user.is_superuser:
            queryset = queryset.exclude(is_superuser=True)
        
        # Filter by role if provided
        role = self.request.query_params.get('role', None)
        if role:
            queryset = queryset.filter(role=role)
        
        # Filter by active status if provided
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Filter by verified status if provided
        is_verified = self.request.query_params.get('is_verified', None)
        if is_verified is not None:
            queryset = queryset.filter(is_verified=is_verified.lower() == 'true')
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Admin can set role during creation
            role = request.data.get('role', 'public')
            if role in ['admin', 'committee', 'staff', 'public']:
                user.role = role
            
            # Admin can set verification status
            is_verified = request.data.get('is_verified', False)
            user.is_verified = bool(is_verified)
            
            user.save()
            
            return Response({
                'success': True,
                'message': 'User created successfully.',
                'user': UserSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def set_password(self, request, pk=None):
        user = self.get_object()
        new_password = request.data.get('new_password')
        
        if not new_password:
            return Response({
                'success': False,
                'error': 'New password is required.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user.set_password(new_password)
        user.save()
        
        return Response({
            'success': True,
            'message': 'Password set successfully.'
        })
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save()
        
        serializer = self.get_serializer(user)
        return Response({
            'success': True,
            'message': 'User activated successfully.',
            'user': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save()
        
        serializer = self.get_serializer(user)
        return Response({
            'success': True,
            'message': 'User deactivated successfully.',
            'user': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        user = self.get_object()
        user.is_verified = True
        user.save()
        
        serializer = self.get_serializer(user)
        return Response({
            'success': True,
            'message': 'User verified successfully.',
            'user': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def unverify(self, request, pk=None):
        user = self.get_object()
        user.is_verified = False
        user.save()
        
        serializer = self.get_serializer(user)
        return Response({
            'success': True,
            'message': 'User unverified successfully.',
            'user': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        verified_users = User.objects.filter(is_verified=True).count()
        
        role_stats = {}
        for role_code, role_name in User.ROLE_CHOICES:
            count = User.objects.filter(role=role_code).count()
            role_stats[role_name] = count
        
        # Ward distribution
        ward_users = {}
        wards = User.objects.values_list('ward', flat=True).distinct()
        for ward in wards:
            if ward:
                count = User.objects.filter(ward=ward).count()
                ward_users[ward] = count
        
        return Response({
            'total_users': total_users,
            'active_users': active_users,
            'verified_users': verified_users,
            'by_role': role_stats,
            'by_ward': ward_users,
        })
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        user = request.user
        serializer = UserSerializer(user)
        return Response(serializer.data)

# ==================== SIMPLIFIED PUBLIC VIEWS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def public_profile(request):
    user = request.user
    data = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name or '',
        'last_name': user.last_name or '',
        'phone': user.phone or '',
        'ward': user.ward or '',
        'county': user.county or '',
        'constituency': user.constituency or '',
        'role': user.role,
    }
    return Response(data)

@api_view(['POST'])
@permission_classes([AllowAny])
def public_login(request):
    try:
        identifier = request.data.get('username') or request.data.get('email')
        password = request.data.get('password')
        
        if not identifier or not password:
            return Response({
                'success': False,
                'error': 'Username/Email and password are required.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = None
        
        # Check if it's an email or username
        if '@' in identifier:
            try:
                user_obj = User.objects.get(email=identifier)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None
        else:
            user = authenticate(username=identifier, password=password)
        
        if user is None:
            return Response({
                'success': False,
                'error': 'Invalid credentials.'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'success': True,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name or '',
                'last_name': user.last_name or '',
                'role': user.role,
                'phone': user.phone or '',
                'ward': user.ward or '',
            }
        })
        
    except Exception as e:
        logger.error(f"Public login error: {str(e)}")
        return Response({
            'success': False,
            'error': 'An error occurred during login'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)