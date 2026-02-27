from rest_framework.permissions import BasePermission
from utils.jwt_utils import decode_token
from authentication.models import User


def get_user_from_request(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header.split(' ')[1]
    payload = decode_token(token)
    if not payload:
        return None
    try:
        user = User.objects.get(id=payload['user_id'], is_active=True)
        return user
    except User.DoesNotExist:
        return None


class IsAuthenticated(BasePermission):
    def has_permission(self, request, view):
        user = get_user_from_request(request)
        if user:
            request.user = user
            return True
        return False


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        user = get_user_from_request(request)
        if user and user.role == 'admin':
            request.user = user
            return True
        return False


class IsSeller(BasePermission):
    def has_permission(self, request, view):
        user = get_user_from_request(request)
        if user and user.role == 'seller':
            request.user = user
            return True
        return False


class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        user = get_user_from_request(request)
        if user and user.role == 'customer':
            request.user = user
            return True
        return False


class IsRider(BasePermission):
    def has_permission(self, request, view):
        user = get_user_from_request(request)
        if user and user.role == 'rider':
            request.user = user
            return True
        return False


class IsSellerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        user = get_user_from_request(request)
        if user and user.role in ['seller', 'admin']:
            request.user = user
            return True
        return False


class IsAuthenticatedAny(BasePermission):
    """Any authenticated user regardless of role"""
    def has_permission(self, request, view):
        user = get_user_from_request(request)
        if user:
            request.user = user
            return True
        return False
