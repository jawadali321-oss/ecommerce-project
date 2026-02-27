from django.urls import path
from .views import (
    CategoryListView, ProductListView, ProductDetailView,
    SellerProductView, SellerProductDetailView, ProductReviewView,
)

urlpatterns = [
    # Public
    path('categories/', CategoryListView.as_view(), name='categories'),
    path('', ProductListView.as_view(), name='product-list'),
    path('<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('<int:pk>/review/', ProductReviewView.as_view(), name='product-review'),

    # Seller management
    path('seller/products/', SellerProductView.as_view(), name='seller-products'),
    path('seller/products/<int:pk>/', SellerProductDetailView.as_view(), name='seller-product-detail'),
]
