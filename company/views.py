from rest_framework.views import APIView
from rest_framework.response import Response
from authentication.models import User
from products.models import Product, Category
from orders.models import Order
from utils.permissions import IsAdmin


class GlobalView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        total_users = User.objects.count()
        verified_users = User.objects.filter(is_verified=True).count()

        users = User.objects.all().values(
            'id', 'name', 'username', 'email', 'role', 'is_verified',
            'is_active', 'created_at', 'last_login'
        )

        return Response({
            'stats': {
                'total_users': total_users,
                'verified_users': verified_users,
                'unverified_users': total_users - verified_users,
                'total_products': Product.objects.count(),
                'total_orders': Order.objects.count(),
                'total_categories': Category.objects.count(),
            },
            'users': list(users)
        })
