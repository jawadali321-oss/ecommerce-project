from django.utils import timezone
from django.db.models import Sum, Count, Avg
from rest_framework.views import APIView
from rest_framework.response import Response

from authentication.models import User, SellerProfile, RiderProfile
from products.models import Product, Category
from orders.models import Order
from utils.permissions import IsAdmin


class AdminDashboardView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        total_users = User.objects.count()
        customers = User.objects.filter(role='customer').count()
        sellers = User.objects.filter(role='seller').count()
        riders = User.objects.filter(role='rider').count()

        total_orders = Order.objects.count()
        pending_orders = Order.objects.filter(status='pending').count()
        delivered_orders = Order.objects.filter(status='delivered').count()

        total_revenue = Order.objects.filter(
            status='delivered'
        ).aggregate(total=Sum('total'))['total'] or 0

        total_products = Product.objects.count()
        active_products = Product.objects.filter(status='active').count()

        pending_sellers = SellerProfile.objects.filter(is_approved=False).count()
        pending_riders = RiderProfile.objects.filter(is_approved=False).count()

        return Response({
            'users': {
                'total': total_users,
                'customers': customers,
                'sellers': sellers,
                'riders': riders,
            },
            'orders': {
                'total': total_orders,
                'pending': pending_orders,
                'delivered': delivered_orders,
            },
            'revenue': str(total_revenue),
            'products': {
                'total': total_products,
                'active': active_products,
            },
            'approvals_pending': {
                'sellers': pending_sellers,
                'riders': pending_riders,
            }
        })


class AdminUserListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        role = request.GET.get('role')
        qs = User.objects.all()
        if role:
            qs = qs.filter(role=role)

        users = list(qs.values(
            'id', 'name', 'email', 'role', 'is_verified', 'is_active', 'created_at', 'last_login'
        ))
        return Response(users)


class AdminUserDetailView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

        data = {
            'id': user.id, 'name': user.name, 'email': user.email,
            'role': user.role, 'phone': user.phone, 'city': user.city,
            'is_verified': user.is_verified, 'is_active': user.is_active,
            'created_at': user.created_at, 'last_login': user.last_login,
        }

        if user.role == 'seller' and hasattr(user, 'seller_profile'):
            sp = user.seller_profile
            data['seller_profile'] = {
                'shop_name': sp.shop_name, 'is_approved': sp.is_approved,
                'total_sales': str(sp.total_sales), 'rating': str(sp.rating),
            }
        elif user.role == 'rider' and hasattr(user, 'rider_profile'):
            rp = user.rider_profile
            data['rider_profile'] = {
                'vehicle_type': rp.vehicle_type, 'is_approved': rp.is_approved,
                'total_deliveries': rp.total_deliveries, 'status': rp.status,
            }

        return Response(data)

    def put(self, request, pk):
        """Activate/deactivate user"""
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

        if 'is_active' in request.data:
            user.is_active = request.data['is_active']
        if 'role' in request.data:
            user.role = request.data['role']
        user.save()
        return Response({'message': 'User updated'})

    def delete(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
            user.delete()
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)
        return Response({'message': 'User deleted'})


class AdminApproveSeller(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk, role='seller')
            sp = user.seller_profile
        except (User.DoesNotExist, SellerProfile.DoesNotExist):
            return Response({'error': 'Seller not found'}, status=404)

        action = request.data.get('action')  # 'approve' or 'reject'
        if action == 'approve':
            sp.is_approved = True
            sp.save()
            return Response({'message': 'Seller approved'})
        elif action == 'reject':
            sp.is_approved = False
            sp.save()
            return Response({'message': 'Seller rejected'})
        return Response({'error': 'action must be approve or reject'}, status=400)


class AdminApproveRider(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk, role='rider')
            rp = user.rider_profile
        except (User.DoesNotExist, RiderProfile.DoesNotExist):
            return Response({'error': 'Rider not found'}, status=404)

        action = request.data.get('action')
        if action == 'approve':
            rp.is_approved = True
            rp.status = 'available'
            rp.save()
            return Response({'message': 'Rider approved'})
        elif action == 'reject':
            rp.is_approved = False
            rp.save()
            return Response({'message': 'Rider rejected'})
        return Response({'error': 'action must be approve or reject'}, status=400)


class AdminCategoryView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        cats = Category.objects.all().values('id', 'name', 'slug', 'is_active', 'created_at')
        return Response(list(cats))

    def post(self, request):
        from django.utils.text import slugify
        name = request.data.get('name')
        if not name:
            return Response({'error': 'name is required'}, status=400)

        slug = slugify(name)
        cat = Category.objects.create(
            name=name,
            slug=slug,
            description=request.data.get('description', ''),
            parent_id=request.data.get('parent_id'),
        )
        return Response({'message': 'Category created', 'id': cat.id}, status=201)

    def put(self, request, pk):
        try:
            cat = Category.objects.get(pk=pk)
        except Category.DoesNotExist:
            return Response({'error': 'Category not found'}, status=404)

        for field in ['name', 'description', 'is_active']:
            if field in request.data:
                setattr(cat, field, request.data[field])
        cat.save()
        return Response({'message': 'Category updated'})

    def delete(self, request, pk):
        try:
            Category.objects.get(pk=pk).delete()
        except Category.DoesNotExist:
            return Response({'error': 'Category not found'}, status=404)
        return Response({'message': 'Category deleted'})


class AdminOrderListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        status_filter = request.GET.get('status')
        qs = Order.objects.all()
        if status_filter:
            qs = qs.filter(status=status_filter)

        orders = list(qs.values(
            'id', 'order_number', 'status', 'total',
            'payment_method', 'payment_status', 'created_at'
        )[:100])
        return Response(orders)


class AdminProductListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        qs = Product.objects.all().select_related('seller', 'category')
        products = [{
            'id': p.id, 'name': p.name, 'price': str(p.price),
            'stock': p.stock, 'status': p.status,
            'seller': p.seller.name, 'category': p.category.name if p.category else None,
        } for p in qs[:100]]
        return Response(products)

    def put(self, request, pk):
        """Admin can change product status"""
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=404)

        if 'status' in request.data:
            product.status = request.data['status']
        if 'is_featured' in request.data:
            product.is_featured = request.data['is_featured']
        product.save()
        return Response({'message': 'Product updated'})
