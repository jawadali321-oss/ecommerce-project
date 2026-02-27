from django.utils.text import slugify
from django.db.models import Q, Avg
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Category, Product, ProductImage, ProductVariant, ProductReview
from utils.permissions import IsAuthenticated, IsSeller, IsAdmin, IsCustomer, IsAuthenticatedAny


# ─── PUBLIC VIEWS (no auth needed) ───────────────────────────────────────────

class CategoryListView(APIView):
    permission_classes = []

    def get(self, request):
        cats = Category.objects.filter(is_active=True, parent=None).values(
            'id', 'name', 'slug', 'description'
        )
        return Response(list(cats))


class ProductListView(APIView):
    """Browse products with filters: category, min_price, max_price, search, sort"""
    permission_classes = []

    def get(self, request):
        qs = Product.objects.filter(status='active').select_related('seller', 'category')

        # Filters
        category = request.GET.get('category')
        search = request.GET.get('search')
        min_price = request.GET.get('min_price')
        max_price = request.GET.get('max_price')
        sort = request.GET.get('sort', 'newest')
        featured = request.GET.get('featured')
        seller_id = request.GET.get('seller_id')

        if category:
            if category.isdigit():
                qs = qs.filter(category__id=category)
            else:  # ✅ FIXED: now correctly nested inside `if category:`
                qs = qs.filter(Q(category__slug=category) | Q(category__name__iexact=category))
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        if min_price:
            qs = qs.filter(price__gte=min_price)
        if max_price:
            qs = qs.filter(price__lte=max_price)
        if featured:
            qs = qs.filter(is_featured=True)
        if seller_id:
            qs = qs.filter(seller_id=seller_id)

        sort_map = {
            'newest': '-created_at',
            'oldest': 'created_at',
            'price_low': 'price',
            'price_high': '-price',
            'popular': '-total_sold',
            'rating': '-rating',
        }
        qs = qs.order_by(sort_map.get(sort, '-created_at'))

        # Pagination
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        total = qs.count()
        start = (page - 1) * per_page
        end = start + per_page

        products = []
        for p in qs[start:end]:
            primary_image = p.images.filter(is_primary=True).first()
            products.append({
                'id': p.id,
                'name': p.name,
                'slug': p.slug,
                'price': str(p.price),
                'compare_price': str(p.compare_price) if p.compare_price else None,
                'discount_percent': p.discount_percent,
                'rating': str(p.rating),
                'total_reviews': p.total_reviews,
                'total_sold': p.total_sold,
                'stock': p.stock,
                'is_in_stock': p.is_in_stock,
                'category': p.category.name if p.category else None,
                'seller': p.seller.name,
                'seller_id': p.seller_id,
                'image': primary_image.image.url if primary_image else None,
            })

        return Response({
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page,
            'products': products
        })


class ProductDetailView(APIView):
    permission_classes = []

    def get(self, request, pk):
        try:
            p = Product.objects.get(pk=pk, status='active')
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=404)

        images = [{'id': img.id, 'url': img.image.url, 'is_primary': img.is_primary}
                  for img in p.images.all()]
        variants = [{'id': v.id, 'name': v.name, 'value': v.value,
                     'price_adjustment': str(v.price_adjustment), 'stock': v.stock}
                    for v in p.variants.all()]
        reviews = []
        for r in p.reviews.select_related('customer').order_by('-created_at')[:10]:
            reviews.append({
                'id': r.id,
                'customer': r.customer.name,
                'rating': r.rating,
                'comment': r.comment,
                'is_verified_purchase': r.is_verified_purchase,
                'created_at': r.created_at,
            })

        seller_profile = getattr(p.seller, 'seller_profile', None)

        return Response({
            'id': p.id,
            'name': p.name,
            'slug': p.slug,
            'description': p.description,
            'price': str(p.price),
            'compare_price': str(p.compare_price) if p.compare_price else None,
            'discount_percent': p.discount_percent,
            'stock': p.stock,
            'sku': p.sku,
            'weight': str(p.weight) if p.weight else None,
            'rating': str(p.rating),
            'total_reviews': p.total_reviews,
            'total_sold': p.total_sold,
            'is_featured': p.is_featured,
            'category': {'id': p.category.id, 'name': p.category.name} if p.category else None,
            'seller': {
                'id': p.seller.id,
                'name': p.seller.name,
                'shop_name': seller_profile.shop_name if seller_profile else None,
                'rating': str(seller_profile.rating) if seller_profile else None,
            },
            'images': images,
            'variants': variants,
            'reviews': reviews,
            'created_at': p.created_at,
        })


# ─── SELLER PRODUCT MANAGEMENT ───────────────────────────────────────────────

class SellerProductView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        """List seller's own products"""
        products = Product.objects.filter(seller=request.user).values(
            'id', 'name', 'price', 'stock', 'status', 'total_sold', 'rating', 'created_at'
        )
        return Response(list(products))

    def post(self, request):
        """Create a new product"""
        data = request.data
        required = ['name', 'description', 'price', 'stock']
        for f in required:
            if not data.get(f):
                return Response({'error': f'{f} is required'}, status=400)

        # Check seller approval
        sp = getattr(request.user, 'seller_profile', None)
        if sp and not sp.is_approved:
            return Response({'error': 'Your seller account is not yet approved'}, status=403)

        slug = slugify(data['name'])
        base_slug = slug
        count = 1
        while Product.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{count}"
            count += 1

        category = None
        if data.get('category_id'):
            try:
                category = Category.objects.get(id=data['category_id'])
            except Category.DoesNotExist:
                pass

        product = Product.objects.create(
            seller=request.user,
            category=category,
            name=data['name'],
            slug=slug,
            description=data['description'],
            price=data['price'],
            compare_price=data.get('compare_price'),
            stock=data['stock'],
            sku=data.get('sku'),
            weight=data.get('weight'),
            is_featured=data.get('is_featured', False),
        )

        return Response({'message': 'Product created', 'product_id': product.id}, status=201)


class SellerProductDetailView(APIView):
    permission_classes = [IsSeller]

    def get_product(self, pk, seller):
        try:
            return Product.objects.get(pk=pk, seller=seller)
        except Product.DoesNotExist:
            return None

    def get(self, request, pk):
        product = self.get_product(pk, request.user)
        if not product:
            return Response({'error': 'Product not found'}, status=404)
        return Response({
            'id': product.id, 'name': product.name, 'price': str(product.price),
            'stock': product.stock, 'status': product.status, 'description': product.description,
        })

    def put(self, request, pk):
        product = self.get_product(pk, request.user)
        if not product:
            return Response({'error': 'Product not found'}, status=404)

        data = request.data
        updatable = ['name', 'description', 'price', 'compare_price', 'stock', 'sku', 'weight', 'status', 'is_featured']
        for field in updatable:
            if field in data:
                setattr(product, field, data[field])

        if data.get('category_id'):
            try:
                product.category = Category.objects.get(id=data['category_id'])
            except Category.DoesNotExist:
                pass
        product.save()
        return Response({'message': 'Product updated'})

    def delete(self, request, pk):
        product = self.get_product(pk, request.user)
        if not product:
            return Response({'error': 'Product not found'}, status=404)
        product.delete()
        return Response({'message': 'Product deleted'})


# ─── REVIEW ──────────────────────────────────────────────────────────────────

class ProductReviewView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request, pk):
        try:
            product = Product.objects.get(pk=pk, status='active')
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=404)

        if ProductReview.objects.filter(product=product, customer=request.user).exists():
            return Response({'error': 'You already reviewed this product'}, status=400)

        rating = request.data.get('rating')
        if not rating or int(rating) not in range(1, 6):
            return Response({'error': 'Rating must be 1-5'}, status=400)

        # Check if verified purchase
        from orders.models import OrderItem
        is_verified = OrderItem.objects.filter(
            order__customer=request.user, product=product, order__status='delivered'
        ).exists()

        review = ProductReview.objects.create(
            product=product,
            customer=request.user,
            rating=int(rating),
            comment=request.data.get('comment', ''),
            is_verified_purchase=is_verified,
        )

        # Update product rating
        avg = ProductReview.objects.filter(product=product).aggregate(avg=Avg('rating'))['avg']
        product.rating = round(avg, 2)
        product.total_reviews = ProductReview.objects.filter(product=product).count()
        product.save(update_fields=['rating', 'total_reviews'])

        return Response({'message': 'Review added', 'review_id': review.id}, status=201)