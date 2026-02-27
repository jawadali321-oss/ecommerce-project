import random
import string
from django.utils import timezone
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Cart, CartItem, Order, OrderItem, ShippingAddress, DeliveryTracking
from products.models import Product, ProductVariant
from authentication.models import User
from utils.permissions import IsAuthenticated, IsCustomer, IsSeller, IsRider, IsAdmin


def generate_order_number():
    return 'ORD-' + ''.join(random.choices(string.digits, k=10))


# ─── CART (Customer only) ─────────────────────────────────────────────────────

class CartView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(customer=request.user)
        items = []
        for item in cart.items.select_related('product', 'variant'):
            primary_image = item.product.images.filter(is_primary=True).first()
            items.append({
                'id': item.id,
                'product_id': item.product.id,
                'product_name': item.product.name,
                'product_image': primary_image.image.url if primary_image else None,
                'variant': f"{item.variant.name}: {item.variant.value}" if item.variant else None,
                'unit_price': str(item.unit_price),
                'quantity': item.quantity,
                'subtotal': str(item.subtotal),
                'stock': item.product.stock,
            })
        return Response({
            'cart_id': cart.id,
            'total_items': cart.total_items,
            'total': str(cart.total),
            'items': items,
        })

    def post(self, request):
        """Add item to cart"""
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))
        variant_id = request.data.get('variant_id')

        if not product_id:
            return Response({'error': 'product_id is required'}, status=400)

        try:
            product = Product.objects.get(id=product_id, status='active')
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=404)

        if not product.is_in_stock:
            return Response({'error': 'Product is out of stock'}, status=400)

        if quantity > product.stock:
            return Response({'error': f'Only {product.stock} items available'}, status=400)

        variant = None
        if variant_id:
            try:
                variant = ProductVariant.objects.get(id=variant_id, product=product)
            except ProductVariant.DoesNotExist:
                return Response({'error': 'Variant not found'}, status=404)

        cart, _ = Cart.objects.get_or_create(customer=request.user)
        existing = CartItem.objects.filter(cart=cart, product=product, variant=variant).first()

        if existing:
            new_qty = existing.quantity + quantity
            if new_qty > product.stock:
                return Response({'error': f'Only {product.stock} items available'}, status=400)
            existing.quantity = new_qty
            existing.save()
        else:
            CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=quantity)

        return Response({'message': 'Item added to cart', 'total_items': cart.total_items})

    def delete(self, request):
        """Clear cart"""
        try:
            cart = Cart.objects.get(customer=request.user)
            cart.items.all().delete()
        except Cart.DoesNotExist:
            pass
        return Response({'message': 'Cart cleared'})


class CartItemView(APIView):
    permission_classes = [IsCustomer]

    def put(self, request, item_id):
        """Update quantity"""
        quantity = request.data.get('quantity')
        if not quantity or int(quantity) < 1:
            return Response({'error': 'Valid quantity required'}, status=400)

        try:
            item = CartItem.objects.get(id=item_id, cart__customer=request.user)
        except CartItem.DoesNotExist:
            return Response({'error': 'Item not found'}, status=404)

        if int(quantity) > item.product.stock:
            return Response({'error': f'Only {item.product.stock} items available'}, status=400)

        item.quantity = int(quantity)
        item.save()
        return Response({'message': 'Quantity updated'})

    def delete(self, request, item_id):
        """Remove item from cart"""
        try:
            item = CartItem.objects.get(id=item_id, cart__customer=request.user)
            item.delete()
        except CartItem.DoesNotExist:
            return Response({'error': 'Item not found'}, status=404)
        return Response({'message': 'Item removed'})


# ─── SHIPPING ADDRESS ────────────────────────────────────────────────────────

class ShippingAddressView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        addresses = ShippingAddress.objects.filter(customer=request.user).values(
            'id', 'full_name', 'phone', 'address_line1', 'address_line2',
            'city', 'state', 'postal_code', 'country', 'is_default'
        )
        return Response(list(addresses))

    def post(self, request):
        data = request.data
        required = ['full_name', 'phone', 'address_line1', 'city', 'postal_code']
        for f in required:
            if not data.get(f):
                return Response({'error': f'{f} is required'}, status=400)

        if data.get('is_default'):
            ShippingAddress.objects.filter(customer=request.user).update(is_default=False)

        addr = ShippingAddress.objects.create(
            customer=request.user,
            full_name=data['full_name'],
            phone=data['phone'],
            address_line1=data['address_line1'],
            address_line2=data.get('address_line2', ''),
            city=data['city'],
            state=data.get('state', ''),
            postal_code=data['postal_code'],
            country=data.get('country', 'Pakistan'),
            is_default=data.get('is_default', False),
        )
        return Response({'message': 'Address added', 'address_id': addr.id}, status=201)

    def delete(self, request, addr_id):
        try:
            addr = ShippingAddress.objects.get(id=addr_id, customer=request.user)
            addr.delete()
        except ShippingAddress.DoesNotExist:
            return Response({'error': 'Address not found'}, status=404)
        return Response({'message': 'Address deleted'})


# ─── CHECKOUT / ORDERS ───────────────────────────────────────────────────────

class CheckoutView(APIView):
    """Place order from cart"""
    permission_classes = [IsCustomer]

    @transaction.atomic
    def post(self, request):
        data = request.data

        try:
            cart = Cart.objects.get(customer=request.user)
        except Cart.DoesNotExist:
            return Response({'error': 'Cart is empty'}, status=400)

        if not cart.items.exists():
            return Response({'error': 'Cart is empty'}, status=400)

        # Validate shipping address
        address_id = data.get('address_id')
        if not address_id:
            return Response({'error': 'address_id is required'}, status=400)

        try:
            address = ShippingAddress.objects.get(id=address_id, customer=request.user)
        except ShippingAddress.DoesNotExist:
            return Response({'error': 'Shipping address not found'}, status=404)

        payment_method = data.get('payment_method', 'cod')

        # Group cart items by seller (one order per seller)
        seller_items = {}
        for item in cart.items.select_related('product__seller', 'variant'):
            seller_id = item.product.seller_id
            if seller_id not in seller_items:
                seller_items[seller_id] = []
            seller_items[seller_id].append(item)

        created_orders = []
        for seller_id, items in seller_items.items():
            seller = User.objects.get(id=seller_id)
            subtotal = sum(item.subtotal for item in items)
            shipping_fee = 150  # flat rate per seller
            total = subtotal + shipping_fee

            order = Order.objects.create(
                order_number=generate_order_number(),
                customer=request.user,
                seller=seller,
                shipping_address=address,
                subtotal=subtotal,
                shipping_fee=shipping_fee,
                total=total,
                payment_method=payment_method,
                payment_status='paid' if payment_method != 'cod' else 'pending',
                status='confirmed',
                confirmed_at=timezone.now(),
                notes=data.get('notes', ''),
            )

            for item in items:
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    variant=item.variant,
                    product_name=item.product.name,
                    product_price=item.unit_price,
                    quantity=item.quantity,
                    subtotal=item.subtotal,
                )
                # Deduct stock
                item.product.stock -= item.quantity
                item.product.total_sold += item.quantity
                item.product.save(update_fields=['stock', 'total_sold'])

            # Initial tracking entry
            DeliveryTracking.objects.create(
                order=order,
                status='Order Confirmed',
                description='Your order has been confirmed and is being prepared.',
            )

            created_orders.append({
                'order_id': order.id,
                'order_number': order.order_number,
                'seller': seller.name,
                'total': str(order.total),
            })

        # Update customer stats
        cp = getattr(request.user, 'customer_profile', None)
        if cp:
            cp.total_orders += len(created_orders)
            cp.total_spent += sum(cart.total for _ in [cart])
            cp.save()

        # Clear cart
        cart.items.all().delete()

        return Response({
            'message': f'{len(created_orders)} order(s) placed successfully',
            'orders': created_orders,
        }, status=201)


class CustomerOrderListView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        status_filter = request.GET.get('status')
        qs = Order.objects.filter(customer=request.user)
        if status_filter:
            qs = qs.filter(status=status_filter)

        orders = []
        for o in qs:
            orders.append({
                'id': o.id,
                'order_number': o.order_number,
                'seller': o.seller.name,
                'total': str(o.total),
                'status': o.status,
                'payment_method': o.payment_method,
                'payment_status': o.payment_status,
                'items_count': o.items.count(),
                'created_at': o.created_at,
            })
        return Response(orders)


class CustomerOrderDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, customer=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)

        items = [{'product': i.product_name, 'quantity': i.quantity,
                  'unit_price': str(i.product_price), 'subtotal': str(i.subtotal)}
                 for i in order.items.all()]

        tracking = [{'status': t.status, 'description': t.description,
                     'location': t.location, 'timestamp': t.timestamp}
                    for t in order.tracking.all()]

        rider_info = None
        if order.rider:
            rp = getattr(order.rider, 'rider_profile', None)
            rider_info = {
                'name': order.rider.name,
                'phone': order.rider.phone,
                'vehicle_type': rp.vehicle_type if rp else None,
                'vehicle_number': rp.vehicle_number if rp else None,
                'current_location': rp.current_location if rp else None,
            }

        return Response({
            'id': order.id,
            'order_number': order.order_number,
            'status': order.status,
            'payment_method': order.payment_method,
            'payment_status': order.payment_status,
            'subtotal': str(order.subtotal),
            'shipping_fee': str(order.shipping_fee),
            'discount': str(order.discount),
            'total': str(order.total),
            'items': items,
            'rider': rider_info,
            'tracking': tracking,
            'created_at': order.created_at,
            'delivered_at': order.delivered_at,
        })

    def post(self, request, pk):
        """Cancel order"""
        try:
            order = Order.objects.get(pk=pk, customer=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)

        if order.status not in ['pending', 'confirmed']:
            return Response({'error': 'Order cannot be cancelled at this stage'}, status=400)

        reason = request.data.get('reason', '')
        order.status = 'cancelled'
        order.cancellation_reason = reason
        order.cancelled_at = timezone.now()
        order.save()

        # Restore stock
        for item in order.items.all():
            item.product.stock += item.quantity
            item.product.total_sold -= item.quantity
            item.product.save(update_fields=['stock', 'total_sold'])

        DeliveryTracking.objects.create(
            order=order,
            status='Order Cancelled',
            description=f'Order cancelled by customer. Reason: {reason}',
        )

        return Response({'message': 'Order cancelled'})


# ─── SELLER ORDER MANAGEMENT ─────────────────────────────────────────────────

class SellerOrderListView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        status_filter = request.GET.get('status')
        qs = Order.objects.filter(seller=request.user)
        if status_filter:
            qs = qs.filter(status=status_filter)

        orders = []
        for o in qs:
            addr = o.shipping_address
            orders.append({
                'id': o.id,
                'order_number': o.order_number,
                'customer': o.customer.name,
                'customer_phone': o.customer.phone,
                'total': str(o.total),
                'status': o.status,
                'payment_method': o.payment_method,
                'items_count': o.items.count(),
                'city': addr.city if addr else None,
                'created_at': o.created_at,
            })
        return Response(orders)


class SellerOrderDetailView(APIView):
    permission_classes = [IsSeller]

    def get(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, seller=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)

        addr = order.shipping_address
        return Response({
            'id': order.id,
            'order_number': order.order_number,
            'status': order.status,
            'customer': {'name': order.customer.name, 'phone': order.customer.phone, 'email': order.customer.email},
            'shipping_address': {
                'full_name': addr.full_name if addr else None,
                'phone': addr.phone if addr else None,
                'address': addr.address_line1 if addr else None,
                'city': addr.city if addr else None,
                'postal_code': addr.postal_code if addr else None,
            },
            'items': [{'product': i.product_name, 'quantity': i.quantity, 'subtotal': str(i.subtotal)}
                      for i in order.items.all()],
            'total': str(order.total),
            'payment_method': order.payment_method,
        })

    def put(self, request, pk):
        """Update order status: confirmed -> processing -> shipped"""
        try:
            order = Order.objects.get(pk=pk, seller=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)

        new_status = request.data.get('status')
        allowed_transitions = {
            'confirmed': 'processing',
            'processing': 'shipped',
        }

        if new_status != allowed_transitions.get(order.status):
            return Response({'error': f'Cannot change status from {order.status} to {new_status}'}, status=400)

        order.status = new_status
        if new_status == 'shipped':
            order.shipped_at = timezone.now()
        order.save()

        DeliveryTracking.objects.create(
            order=order,
            status=new_status.replace('_', ' ').title(),
            description=request.data.get('description', ''),
        )

        return Response({'message': f'Order status updated to {new_status}'})


class SellerAssignRiderView(APIView):
    """Seller assigns an available rider to the order"""
    permission_classes = [IsSeller]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, seller=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)

        if order.status != 'processing':
            return Response({'error': 'Order must be in processing state to assign rider'}, status=400)

        rider_id = request.data.get('rider_id')
        if not rider_id:
            return Response({'error': 'rider_id is required'}, status=400)

        try:
            rider = User.objects.get(id=rider_id, role='rider')
            if not rider.rider_profile.is_approved or rider.rider_profile.status != 'available':
                return Response({'error': 'Rider is not available'}, status=400)
        except (User.DoesNotExist, AttributeError):
            return Response({'error': 'Rider not found'}, status=404)

        order.rider = rider
        order.save(update_fields=['rider'])

        # Set rider to busy
        rider.rider_profile.status = 'busy'
        rider.rider_profile.save(update_fields=['status'])

        return Response({'message': f'Rider {rider.name} assigned to order'})


class AvailableRidersView(APIView):
    """Seller can see available riders"""
    permission_classes = [IsSeller]

    def get(self, request):
        riders = User.objects.filter(
            role='rider', rider_profile__is_approved=True, rider_profile__status='available'
        ).select_related('rider_profile')

        data = [{
            'id': r.id,
            'name': r.name,
            'phone': r.phone,
            'vehicle_type': r.rider_profile.vehicle_type,
            'vehicle_number': r.rider_profile.vehicle_number,
            'total_deliveries': r.rider_profile.total_deliveries,
            'rating': str(r.rider_profile.rating),
        } for r in riders]

        return Response(data)


# ─── RIDER DELIVERY MANAGEMENT ───────────────────────────────────────────────

class RiderDeliveryListView(APIView):
    permission_classes = [IsRider]

    def get(self, request):
        status_filter = request.GET.get('status')
        qs = Order.objects.filter(rider=request.user)
        if status_filter:
            qs = qs.filter(status=status_filter)
        else:
            qs = qs.filter(status__in=['shipped', 'out_for_delivery'])

        orders = []
        for o in qs:
            addr = o.shipping_address
            orders.append({
                'id': o.id,
                'order_number': o.order_number,
                'customer_name': o.customer.name,
                'customer_phone': o.customer.phone,
                'delivery_address': f"{addr.address_line1}, {addr.city}" if addr else None,
                'total': str(o.total),
                'payment_method': o.payment_method,
                'status': o.status,
                'created_at': o.created_at,
            })
        return Response(orders)


class RiderDeliveryUpdateView(APIView):
    permission_classes = [IsRider]

    def put(self, request, pk):
        """Rider updates delivery status"""
        try:
            order = Order.objects.get(pk=pk, rider=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)

        new_status = request.data.get('status')
        allowed = {
            'shipped': 'out_for_delivery',
            'out_for_delivery': 'delivered',
        }

        if new_status != allowed.get(order.status):
            return Response({'error': f'Cannot update from {order.status} to {new_status}'}, status=400)

        order.status = new_status
        if new_status == 'delivered':
            order.delivered_at = timezone.now()
            if order.payment_method == 'cod':
                order.payment_status = 'paid'

            # Update rider stats
            rp = request.user.rider_profile
            rp.total_deliveries += 1
            rp.status = 'available'
            rp.save(update_fields=['total_deliveries', 'status'])

            # Update seller total sales
            sp = getattr(order.seller, 'seller_profile', None)
            if sp:
                sp.total_sales += order.total
                sp.save(update_fields=['total_sales'])

        order.save()

        DeliveryTracking.objects.create(
            order=order,
            status=new_status.replace('_', ' ').title(),
            description=request.data.get('description', ''),
            location=request.data.get('location', ''),
        )

        return Response({'message': f'Delivery status updated to {new_status}'})


class RiderStatusView(APIView):
    """Rider updates their availability status"""
    permission_classes = [IsRider]

    def put(self, request):
        new_status = request.data.get('status')
        if new_status not in ['available', 'offline']:
            return Response({'error': 'Status must be available or offline'}, status=400)

        rp = request.user.rider_profile
        if rp.status == 'busy':
            return Response({'error': 'Cannot change status while on active delivery'}, status=400)

        rp.status = new_status
        if request.data.get('latitude'):
            rp.latitude = request.data['latitude']
        if request.data.get('longitude'):
            rp.longitude = request.data['longitude']
        if request.data.get('current_location'):
            rp.current_location = request.data['current_location']
        rp.save()

        return Response({'message': f'Status updated to {new_status}'})
