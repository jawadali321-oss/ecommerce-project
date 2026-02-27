from django.urls import path
from .views import (
    AdminDashboardView, AdminUserListView, AdminUserDetailView,
    AdminApproveSeller, AdminApproveRider,
    AdminCategoryView, AdminOrderListView, AdminProductListView,
)

urlpatterns = [
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('users/', AdminUserListView.as_view(), name='admin-users'),
    path('users/<int:pk>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('sellers/<int:pk>/approve/', AdminApproveSeller.as_view(), name='admin-approve-seller'),
    path('riders/<int:pk>/approve/', AdminApproveRider.as_view(), name='admin-approve-rider'),
    path('categories/', AdminCategoryView.as_view(), name='admin-categories'),
    path('categories/<int:pk>/', AdminCategoryView.as_view(), name='admin-category-detail'),
    path('orders/', AdminOrderListView.as_view(), name='admin-orders'),
    path('products/', AdminProductListView.as_view(), name='admin-products'),
    path('products/<int:pk>/', AdminProductListView.as_view(), name='admin-product-detail'),
]
