import random
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import User, SellerProfile, RiderProfile, CustomerProfile
from utils.jwt_utils import generate_token, decode_token
from utils.permissions import IsAuthenticated, IsAdmin


def send_otp_email(email, otp, purpose="verification"):
    subject_map = {
        "verification": "Verify Your Email - OTP",
        "reset": "Password Reset OTP",
    }
    send_mail(
        subject=subject_map.get(purpose, "OTP"),
        message=f"Your OTP is: {otp}\nThis OTP is valid for 5 minutes.",
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[email],
        fail_silently=False,
    )


class RegisterView(APIView):
    """
    Register as customer, seller, or rider.
    Required fields: name, email, password, role
    Seller extra: shop_name, shop_address, shop_city
    Rider extra: vehicle_type, vehicle_number, cnic
    Customer extra: (optional) date_of_birth
    """
    permission_classes = []

    def post(self, request):
        data = request.data
        required = ['name', 'email', 'password', 'role']
        for field in required:
            if not data.get(field):
                return Response({'error': f'{field} is required'}, status=400)

        role = data['role']
        if role not in ['customer', 'seller', 'rider']:
            return Response({'error': 'Role must be customer, seller, or rider'}, status=400)

        if User.objects.filter(email=data['email']).exists():
            return Response({'error': 'Email already registered'}, status=400)

        if data.get('username') and User.objects.filter(username=data['username']).exists():
            return Response({'error': 'Username already taken'}, status=400)

        # Validate role-specific required fields
        if role == 'seller' and not data.get('shop_name'):
            return Response({'error': 'shop_name is required for sellers'}, status=400)

        otp = str(random.randint(100000, 999999))

        user = User.objects.create(
            name=data['name'],
            email=data['email'],
            password=data['password'],
            role=role,
            phone=data.get('phone'),
            username=data.get('username'),
            address=data.get('address'),
            city=data.get('city'),
            country=data.get('country'),
            otp=otp,
            otp_created_at=timezone.now(),
        )

        # Create role-specific profile
        if role == 'seller':
            SellerProfile.objects.create(
                user=user,
                shop_name=data['shop_name'],
                shop_description=data.get('shop_description', ''),
                shop_address=data.get('shop_address', ''),
                shop_city=data.get('shop_city', ''),
                business_registration_no=data.get('business_registration_no', ''),
                tax_id=data.get('tax_id', ''),
                bank_account_no=data.get('bank_account_no', ''),
                bank_name=data.get('bank_name', ''),
            )
        elif role == 'rider':
            RiderProfile.objects.create(
                user=user,
                vehicle_type=data.get('vehicle_type', 'bike'),
                vehicle_number=data.get('vehicle_number', ''),
                cnic=data.get('cnic', ''),
                license_number=data.get('license_number', ''),
            )
        elif role == 'customer':
            CustomerProfile.objects.create(
                user=user,
                date_of_birth=data.get('date_of_birth'),
            )

        try:
            send_otp_email(user.email, otp, "verification")
        except Exception:
            pass  # Don't fail registration if email fails

        return Response({
            'message': 'Registration successful. OTP sent to your email.',
            'user_id': user.id,
            'email': user.email,
            'role': user.role,
        }, status=201)


class VerifyOTPView(APIView):
    permission_classes = []

    def post(self, request):
        email = request.data.get('email')
        otp = request.data.get('otp')

        if not email or not otp:
            return Response({'error': 'email and otp are required'}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

        if user.is_verified:
            return Response({'message': 'Already verified'}, status=200)

        if not user.is_otp_valid(otp):
            return Response({'error': 'Invalid or expired OTP'}, status=400)

        user.is_verified = True
        user.otp = None
        user.otp_created_at = None
        user.save()

        # Auto-approve customers; sellers/riders need admin approval
        token = generate_token(user)
        return Response({
            'message': 'Email verified successfully',
            'token': token,
            'role': user.role,
            'needs_approval': user.role in ['seller', 'rider'],
        }, status=200)


class LoginView(APIView):
    permission_classes = []

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({'error': 'email and password are required'}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid credentials'}, status=401)

        if not check_password(password, user.password):
            return Response({'error': 'Invalid credentials'}, status=401)

        if not user.is_verified:
            return Response({'error': 'Please verify your email first'}, status=403)

        if not user.is_active:
            return Response({'error': 'Account is deactivated'}, status=403)

        # Check seller/rider approval
        if user.role == 'seller':
            profile = getattr(user, 'seller_profile', None)
            if profile and not profile.is_approved:
                return Response({'error': 'Your seller account is pending admin approval'}, status=403)
        elif user.role == 'rider':
            profile = getattr(user, 'rider_profile', None)
            if profile and not profile.is_approved:
                return Response({'error': 'Your rider account is pending admin approval'}, status=403)

        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        token = generate_token(user)

        response_data = {
            'message': 'Login successful',
            'token': token,
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'role': user.role,
                'username': user.username,
            }
        }

        # Add role-specific profile info
        if user.role == 'seller' and hasattr(user, 'seller_profile'):
            response_data['shop'] = {
                'shop_name': user.seller_profile.shop_name,
                'is_approved': user.seller_profile.is_approved,
            }
        elif user.role == 'rider' and hasattr(user, 'rider_profile'):
            response_data['rider'] = {
                'status': user.rider_profile.status,
                'vehicle_type': user.rider_profile.vehicle_type,
            }

        return Response(response_data, status=200)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # JWT is stateless; client deletes token
        return Response({'message': 'Logged out successfully'}, status=200)


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        data = {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'username': user.username,
            'phone': user.phone,
            'role': user.role,
            'address': user.address,
            'city': user.city,
            'country': user.country,
            'is_verified': user.is_verified,
            'last_login': user.last_login,
            'created_at': user.created_at,
        }

        if user.role == 'seller' and hasattr(user, 'seller_profile'):
            sp = user.seller_profile
            data['seller_profile'] = {
                'shop_name': sp.shop_name,
                'shop_description': sp.shop_description,
                'shop_address': sp.shop_address,
                'shop_city': sp.shop_city,
                'is_approved': sp.is_approved,
                'total_sales': str(sp.total_sales),
                'rating': str(sp.rating),
            }
        elif user.role == 'rider' and hasattr(user, 'rider_profile'):
            rp = user.rider_profile
            data['rider_profile'] = {
                'vehicle_type': rp.vehicle_type,
                'vehicle_number': rp.vehicle_number,
                'status': rp.status,
                'is_approved': rp.is_approved,
                'total_deliveries': rp.total_deliveries,
                'rating': str(rp.rating),
            }
        elif user.role == 'customer' and hasattr(user, 'customer_profile'):
            cp = user.customer_profile
            data['customer_profile'] = {
                'total_orders': cp.total_orders,
                'total_spent': str(cp.total_spent),
            }

        return Response(data)

    def put(self, request):
        user = request.user
        data = request.data
        updatable = ['name', 'phone', 'address', 'city', 'country', 'username']
        for field in updatable:
            if field in data:
                setattr(user, field, data[field])
        user.save()

        # Update role profile
        if user.role == 'seller' and hasattr(user, 'seller_profile'):
            sp = user.seller_profile
            seller_fields = ['shop_description', 'shop_address', 'shop_city', 'bank_account_no', 'bank_name']
            for field in seller_fields:
                if field in data:
                    setattr(sp, field, data[field])
            sp.save()
        elif user.role == 'rider' and hasattr(user, 'rider_profile'):
            rp = user.rider_profile
            rider_fields = ['vehicle_type', 'vehicle_number', 'current_location', 'latitude', 'longitude', 'status']
            for field in rider_fields:
                if field in data:
                    setattr(rp, field, data[field])
            rp.save()

        return Response({'message': 'Profile updated successfully'})


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')

        if not old_password or not new_password:
            return Response({'error': 'old_password and new_password are required'}, status=400)

        if not check_password(old_password, user.password):
            return Response({'error': 'Old password is incorrect'}, status=400)

        user.password = make_password(new_password)
        user.save(update_fields=['password'])
        return Response({'message': 'Password changed successfully'})


class ForgotPasswordView(APIView):
    permission_classes = []

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'email is required'}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'message': 'If account exists, OTP has been sent'}, status=200)

        otp = str(random.randint(100000, 999999))
        user.otp = otp
        user.otp_created_at = timezone.now()
        user.save(update_fields=['otp', 'otp_created_at'])

        try:
            send_otp_email(email, otp, "reset")
        except Exception:
            pass

        return Response({'message': 'OTP sent to your email'}, status=200)


class ResetPasswordView(APIView):
    permission_classes = []

    def post(self, request):
        email = request.data.get('email')
        otp = request.data.get('otp')
        new_password = request.data.get('new_password')

        if not all([email, otp, new_password]):
            return Response({'error': 'email, otp, and new_password are required'}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

        if not user.is_otp_valid(otp):
            return Response({'error': 'Invalid or expired OTP'}, status=400)

        user.password = make_password(new_password)
        user.otp = None
        user.otp_created_at = None
        user.save()

        return Response({'message': 'Password reset successfully'})


class ResendOTPView(APIView):
    permission_classes = []

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'email is required'}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

        otp = str(random.randint(100000, 999999))
        user.otp = otp
        user.otp_created_at = timezone.now()
        user.save(update_fields=['otp', 'otp_created_at'])

        try:
            send_otp_email(email, otp)
        except Exception:
            pass

        return Response({'message': 'OTP resent'})


class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        password = request.data.get('password')
        if not password or not check_password(password, user.password):
            return Response({'error': 'Invalid password'}, status=400)
        user.delete()
        return Response({'message': 'Account deleted'})
