# 🛒 Ecommerce API Reference

Base URL: `http://localhost:8000/api/`

Auth Header: `Authorization: Bearer <token>`

---

## 🔐 AUTHENTICATION (`/api/auth/`)

### POST `/auth/register/`
Register as **customer**, **seller**, or **rider**.

**Customer body:**
```json
{
  "name": "Ali Khan", "email": "ali@gmail.com",
  "password": "Pass123", "role": "customer",
  "phone": "03001234567", "city": "Lahore"
}
```

**Seller body (extra required):**
```json
{
  "name": "Ahmed", "email": "ahmed@shop.com",
  "password": "Pass123", "role": "seller",
  "phone": "03001234567",
  "shop_name": "Ahmed Electronics",
  "shop_address": "Main Market, Lahore",
  "shop_city": "Lahore",
  "bank_account_no": "0011234567890",
  "bank_name": "HBL"
}
```

**Rider body (extra required):**
```json
{
  "name": "Usman", "email": "usman@rider.com",
  "password": "Pass123", "role": "rider",
  "phone": "03001234567",
  "vehicle_type": "bike",
  "vehicle_number": "LHR-1234",
  "cnic": "3520112345671"
}
```
Response: `201` → `{ user_id, email, role, message }`

---

### POST `/auth/verify-otp/`
```json
{ "email": "ali@gmail.com", "otp": "123456" }
```
Response: `{ token, role, needs_approval }`

---

### POST `/auth/resend-otp/`
```json
{ "email": "ali@gmail.com" }
```

---

### POST `/auth/login/`
```json
{ "email": "ali@gmail.com", "password": "Pass123" }
```
Response: `{ token, user: { id, name, email, role } }`

> ⚠️ Sellers and Riders must be **approved by admin** to login.

---

### POST `/auth/logout/` 🔒
Clears session (client deletes token).

---

### GET/PUT `/auth/profile/` 🔒
GET → Full profile with role-specific data  
PUT body (any updatable fields):
```json
{ "phone": "03009999999", "city": "Karachi" }
```
Seller PUT extra: `shop_description, shop_address, bank_account_no`  
Rider PUT extra: `status (available/offline), current_location, latitude, longitude`

---

### POST `/auth/change-password/` 🔒
```json
{ "old_password": "Pass123", "new_password": "NewPass456" }
```

---

### POST `/auth/forgot-password/`
```json
{ "email": "ali@gmail.com" }
```

---

### POST `/auth/reset-password/`
```json
{ "email": "ali@gmail.com", "otp": "123456", "new_password": "NewPass456" }
```

---

### DELETE `/auth/delete-account/` 🔒
```json
{ "password": "Pass123" }
```

---

## 🛍️ PRODUCTS (`/api/products/`)

### GET `/products/` — Public
Browse all products with filters.

Query params:
- `search=phone` — search by name/description
- `category=electronics` — category slug or id
- `min_price=500&max_price=5000`
- `sort=newest|oldest|price_low|price_high|popular|rating`
- `featured=true`
- `seller_id=3`
- `page=1&per_page=20`

---

### GET `/products/<id>/` — Public
Full product detail with images, variants, reviews.

---

### GET `/products/categories/` — Public
All active categories.

---

### POST `/products/<id>/review/` 🔒 (Customer only)
```json
{ "rating": 5, "comment": "Excellent product!" }
```
`is_verified_purchase` auto-set if customer has a delivered order with this product.

---

### GET `/products/seller/products/` 🔒 (Seller only)
List seller's own products.

### POST `/products/seller/products/` 🔒 (Seller only)
```json
{
  "name": "Samsung Galaxy A15",
  "description": "Great budget phone...",
  "price": 45000,
  "compare_price": 52000,
  "stock": 25,
  "category_id": 1,
  "sku": "SAM-A15-BLK",
  "weight": 0.2
}
```

### GET/PUT/DELETE `/products/seller/products/<id>/` 🔒 (Seller only)
PUT: update any product field  
DELETE: remove product

---

## 🛒 ORDERS (`/api/orders/`)

### CUSTOMER FLOW

#### GET/POST/DELETE `/orders/cart/` 🔒 (Customer)
GET → current cart with items and total  
POST → add item:
```json
{ "product_id": 5, "quantity": 2, "variant_id": 3 }
```
DELETE → clear cart

#### PUT/DELETE `/orders/cart/items/<item_id>/` 🔒 (Customer)
PUT → `{ "quantity": 3 }`  
DELETE → remove item

---

#### GET/POST `/orders/addresses/` 🔒 (Customer)
POST → Add shipping address:
```json
{
  "full_name": "Ali Khan",
  "phone": "03001234567",
  "address_line1": "House 12, Street 5, DHA",
  "city": "Lahore",
  "postal_code": "54000",
  "country": "Pakistan",
  "is_default": true
}
```

#### DELETE `/orders/addresses/<id>/` 🔒 (Customer)

---

#### POST `/orders/checkout/` 🔒 (Customer)
Places order from cart. Auto-splits by seller.
```json
{
  "address_id": 2,
  "payment_method": "cod",
  "notes": "Please deliver before 5pm"
}
```
`payment_method`: `cod | card | wallet | bank_transfer`

Response: `{ orders: [{ order_id, order_number, seller, total }] }`

---

#### GET `/orders/my-orders/` 🔒 (Customer)
Query: `?status=delivered`

#### GET `/orders/my-orders/<id>/` 🔒 (Customer)
Full order with items, tracking timeline, rider info.

#### POST `/orders/my-orders/<id>/` 🔒 (Customer)
Cancel order (only if pending/confirmed):
```json
{ "reason": "Changed my mind" }
```

---

### SELLER FLOW

#### GET `/orders/seller/orders/` 🔒 (Seller)
Query: `?status=confirmed`

Status options: `pending | confirmed | processing | shipped | out_for_delivery | delivered | cancelled`

#### GET `/orders/seller/orders/<id>/` 🔒 (Seller)
Order detail with customer + shipping info.

#### PUT `/orders/seller/orders/<id>/` 🔒 (Seller)
Update order status (step by step):
- `confirmed` → `processing` (start packing)
- `processing` → `shipped` (handed to rider)
```json
{ "status": "processing", "description": "Order packed and ready" }
```

#### POST `/orders/seller/orders/<id>/assign-rider/` 🔒 (Seller)
```json
{ "rider_id": 7 }
```

#### GET `/orders/seller/available-riders/` 🔒 (Seller)
List of approved + available riders.

---

### RIDER FLOW

#### GET `/orders/rider/deliveries/` 🔒 (Rider)
Active deliveries assigned to rider.  
Query: `?status=out_for_delivery`

#### PUT `/orders/rider/deliveries/<id>/` 🔒 (Rider)
Update delivery:
- `shipped` → `out_for_delivery` (picked up)
- `out_for_delivery` → `delivered`
```json
{
  "status": "out_for_delivery",
  "location": "Main Boulevard Lahore",
  "description": "Package picked up from seller"
}
```

#### PUT `/orders/rider/status/` 🔒 (Rider)
```json
{
  "status": "available",
  "latitude": 31.5204,
  "longitude": 74.3587,
  "current_location": "Gulberg, Lahore"
}
```

---

## 🛠️ ADMIN PANEL (`/api/admin-panel/`)

All endpoints require Admin token.

### GET `/admin-panel/dashboard/`
Platform stats: users, orders, revenue, products, pending approvals.

### GET `/admin-panel/users/`
Query: `?role=seller`

### GET/PUT/DELETE `/admin-panel/users/<id>/`
PUT: `{ "is_active": false }` — ban/unban user

### POST `/admin-panel/sellers/<id>/approve/`
```json
{ "action": "approve" }
```
or `"action": "reject"`

### POST `/admin-panel/riders/<id>/approve/`
```json
{ "action": "approve" }
```

### GET/POST `/admin-panel/categories/`
POST: `{ "name": "Electronics", "description": "..." }`

### PUT/DELETE `/admin-panel/categories/<id>/`

### GET `/admin-panel/orders/`
Query: `?status=delivered`

### GET/PUT `/admin-panel/products/`
PUT `<id>`: `{ "status": "inactive", "is_featured": true }`

---

## 🌐 GLOBAL VIEW (`/api/global/`) 🔒 Admin
Platform-wide stats + all users.

---

## 📦 Order Status Flow

```
Customer Places Order
        ↓
   [pending] → Payment confirmed → [confirmed]
        ↓
   Seller packs → [processing]
        ↓
   Seller assigns rider → Rider picks up → [shipped]
        ↓
   Rider starts delivery → [out_for_delivery]
        ↓
   Rider delivers → [delivered] ✅
```

COD payment status changes to **paid** upon delivery.

---

## 👤 Role Permissions Summary

| Action | Customer | Seller | Rider | Admin |
|--------|----------|--------|-------|-------|
| Browse products | ✅ | ✅ | ✅ | ✅ |
| Add to cart | ✅ | ❌ | ❌ | ❌ |
| Place order | ✅ | ❌ | ❌ | ❌ |
| Cancel order | ✅ | ❌ | ❌ | ✅ |
| Write review | ✅ | ❌ | ❌ | ❌ |
| Add product | ❌ | ✅ | ❌ | ❌ |
| Manage orders | ❌ | ✅ | ❌ | ✅ |
| Assign rider | ❌ | ✅ | ❌ | ✅ |
| Update delivery | ❌ | ❌ | ✅ | ❌ |
| Approve sellers/riders | ❌ | ❌ | ❌ | ✅ |
| Ban users | ❌ | ❌ | ❌ | ✅ |

---

## 🚀 Setup Instructions

```bash
# 1. Install dependencies
pip install django djangorestframework pyjwt pillow

# 2. Setup Django settings
# Add to INSTALLED_APPS: authentication, products, orders, adminpanel

# 3. Run migrations
python manage.py makemigrations authentication products orders adminpanel
python manage.py migrate

# 4. Create admin user (run in shell)
python manage.py shell
>>> from authentication.models import User
>>> User.objects.create(name='Admin', email='admin@shop.com', password='admin123', role='admin', is_verified=True)

# 5. Run server
python manage.py runserver
```
