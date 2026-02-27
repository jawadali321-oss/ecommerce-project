from django.urls import path
from .views import (
    CartView, CartItemView,
    ShippingAddressView, CheckoutView,
    CustomerOrderListView, CustomerOrderDetailView,
    SellerOrderListView, SellerOrderDetailView,
    SellerAssignRiderView, AvailableRidersView,
    RiderDeliveryListView, RiderDeliveryUpdateView, RiderStatusView,
)

urlpatterns = [
    # Customer: Cart
    path('cart/', CartView.as_view(), name='cart'),
    path('cart/items/<int:item_id>/', CartItemView.as_view(), name='cart-item'),

    # Customer: Shipping Addresses
    path('addresses/', ShippingAddressView.as_view(), name='addresses'),
    path('addresses/<int:addr_id>/', ShippingAddressView.as_view(), name='address-detail'),

    # Customer: Checkout & Orders
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    path('my-orders/', CustomerOrderListView.as_view(), name='customer-orders'),
    path('my-orders/<int:pk>/', CustomerOrderDetailView.as_view(), name='customer-order-detail'),

    # Seller: Orders
    path('seller/orders/', SellerOrderListView.as_view(), name='seller-orders'),
    path('seller/orders/<int:pk>/', SellerOrderDetailView.as_view(), name='seller-order-detail'),
    path('seller/orders/<int:pk>/assign-rider/', SellerAssignRiderView.as_view(), name='assign-rider'),
    path('seller/available-riders/', AvailableRidersView.as_view(), name='available-riders'),

    # Rider: Deliveries
    path('rider/deliveries/', RiderDeliveryListView.as_view(), name='rider-deliveries'),
    path('rider/deliveries/<int:pk>/', RiderDeliveryUpdateView.as_view(), name='rider-delivery-update'),
    path('rider/status/', RiderStatusView.as_view(), name='rider-status'),
]
