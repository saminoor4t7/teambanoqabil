# Medical Panda — Django Backend

A runnable Django + DRF backend for the Medical Panda platform, structured
as **separate apps under one project**, with `customer`, `medical_store`
(pharmacy) and `rider` as the three role-facing apps, interconnected
through two shared apps rather than importing each other directly.

## Project layout

```
medical_panda_backend/
├── manage.py
├── config/                # project settings, root urls, wsgi/asgi
├── apps/
│   ├── accounts/          # shared identity: one User model + role field, OTP, audit log
│   ├── catalog/           # shared reference data: Medicine, Category, Brand
│   ├── customer/          # CustomerProfile, Address, Prescription(+Items), Cart
│   ├── medical_store/     # PharmacyProfile, InventoryItem, PrescriptionReview, DemandForecast
│   ├── rider/             # RiderProfile, RiderLocationPing, DeliveryOffer
│   └── orders/            # Order, OrderItem, Delivery, Refund — the interconnection hub
├── requirements.txt
└── .env.example
```

## How the three apps are interconnected

Rather than `customer`, `medical_store`, and `rider` importing each
other's models directly (which would create three-way circular imports),
they're wired together through two shared layers:

1. **`accounts.User`** — every profile (`CustomerProfile`, `PharmacyProfile`,
   `RiderProfile`) is a `OneToOneField` onto the same `User`/`role` model,
   so "who is this person" is always answered the same way across apps.
2. **`orders.Order` / `orders.Delivery`** — the hub model. `Order` has
   FKs to `customer.CustomerProfile` and `medical_store.PharmacyProfile`;
   `Delivery` has an FK to `rider.RiderProfile`. Each role app only ever
   reads/writes through this hub (e.g. `medical_store.services.mark_ready_for_pickup`
   calls into `rider.services.request_rider_assignment`), so you can
   still trace the full **customer → pharmacy → rider** journey end to end.

This mirrors FR-10 (order lifecycle), the "AI Rider Assignment" flow, and
the delivery-tracking loop described in the SRS/strategy deck.

## Order lifecycle (FR-10)

```
Pending → Under Review → Accepted → Preparing → Ready for Pickup
        → Picked Up → On the Way → Delivered   (or → Cancelled)
```

- `customer` app creates the order (`Pending`).
- `medical_store.services` moves it through `Accepted → Preparing → Ready
  for Pickup`, and `mark_ready_for_pickup` triggers rider dispatch.
- `rider.services` handles `request_rider_assignment` → `Picked Up → On
  the Way → Delivered`.
- Every transition is written to `OrderStatusHistory` for audit (FR-19).

## AI integration points (kept out of Django's write path on purpose)

Per the architecture slide ("Django remains the main business backend;
AI becomes a specialized service"), Django never lets an LLM/OCR model
write directly into business tables. The only touchpoints are:

- `apps/customer/services.py::request_ai_prescription_extraction` — calls
  the separate AI microservice (`AI_SERVICE_BASE_URL`) and stores the raw
  result on `Prescription.ai_raw_response`. A pharmacist then confirms
  individual `PrescriptionItem` rows via `medical_store.services.verify_prescription`.
- `apps/rider/services.py::_score_rider` / `predict_eta` — placeholder
  heuristics standing in for the Dispatch/ETA Intelligence service; swap
  these for HTTP calls to the AI service.
- `medical_store.DemandForecast` — a plain table the AI service's
  scheduled forecasting job writes into; Django just serves it.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py makemigrations accounts catalog customer medical_store rider orders
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

> Note: this sandbox has no internet access, so dependencies couldn't be
> pip-installed or `migrate` run here — every file was syntax-checked
> (`ast.parse`) instead. Run the commands above locally to generate
> migrations and confirm the models.

## Key API surface

| Area | Endpoint |
|---|---|
| Register / login | `POST /api/accounts/register/`, `POST /api/auth/token/`, OTP: `/api/accounts/otp/request/` + `/otp/verify/` |
| Medicine search | `GET /api/catalog/medicines/?q=panadol` |
| Upload prescription | `POST /api/customer/prescriptions/` |
| Prescription → cart | `POST /api/customer/prescriptions/<id>/build-cart/` |
| Cart | `GET/POST /api/customer/cart/` |
| Place order | `POST /api/customer/orders/place/` |
| Pharmacy incoming orders | `GET /api/pharmacy/orders/incoming/` |
| Pharmacy order transitions | `POST /api/pharmacy/orders/<id>/accept|preparing|ready-for-pickup|reject/` |
| Verify prescription | `POST /api/pharmacy/prescriptions/<id>/verify/` |
| Inventory | `/api/pharmacy/inventory/` |
| Demand forecast | `GET /api/pharmacy/forecasts/` |
| Rider offers | `GET /api/rider/offers/`, `POST /api/rider/offers/<id>/respond/` |
| Rider delivery transitions | `POST /api/rider/deliveries/<order_id>/confirm-pickup|start|confirm-delivered/` |
| Rider location | `POST /api/rider/location/` |
| Order tracking (any role) | `GET /api/orders/<id>/` |

## Not yet built (flagged, not silently skipped)

- Support-ticket/live-chat app (FR-15) and Fraud/AI-analytics app (FR-16,
  FR-20) — same pattern as above (own app + hub FK into `orders`), left
  out to keep this first pass reviewable.
- Payment gateway callbacks (Stripe/JazzCash/Easypaisa) — `Order.payment_method`
  and `is_paid` are modeled; wiring real gateway webhooks is a follow-up.
- Actual OCR/LLM/forecast microservice — only the Django-side contract
  (`AI_SERVICE_BASE_URL`, stored raw responses, confidence fields) is here.
