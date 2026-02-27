from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from company.views import GlobalView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('authentication.urls')),
    path('api/products/', include('products.urls')),
    path('api/orders/', include('orders.urls')),
    path('api/admin-panel/', include('adminpanel.urls')),
    path('api/global/', GlobalView.as_view(), name='global-view'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
