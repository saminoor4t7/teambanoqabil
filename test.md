# Medical Panda — Full API Test Report

**Project:** teambanoqabil (Medical Panda — Medicine Delivery Backend)
**Test date:** 23 Aug 2026
**Environment:** Windows 11 · Python 3.14.5 · Django 5.2.17 · DRF + SimpleJWT · SQLite (`db.sqlite3`)
**Server:** `python manage.py runserver 127.0.0.1:8000 --noreload` (DEBUG=True)
**Method:** Black-box testing of every endpoint via HTTP (PowerShell `Invoke-RestMethod` / `curl.exe`), plus Django DB inspection to verify side effects.

**Test accounts created** (`seed_test_users.py`, kept in repo root):

| Username | Password | Role |
|---|---|---|
| `admin` | `Admin@12345` | admin (superuser) |
| `cust1` | `Cust@12345` | customer |
| `pharm1` / `pharm2` | `Pharm@12345` | pharmacy |
| `rider1` / `rider2` | `Rider@12345` | rider |
| `testuser_otp` | `Test@12345` | customer (via OTP registration flow) |

> ⚠️ NOTE: URLs have **no `/api/` prefix**, contrary to the README. All routes below are as actually mounted in `config/urls.py`.

---

## 1. Executive Summary

- **73 test cases executed** across auth, catalog, customer, pharmacy, rider, and orders.
- **Core happy path works end-to-end:** register (email OTP) → login → browse catalog → cart → place order → pharmacy accept/preparing/ready → rider dispatch → pickup → on the way → delivered (COD auto-paid) → refund request. ✅
- **3 server crashes (HTTP 500)**, **2 confirmed security bugs**, **multiple missing state guards**, and **several missing features** documented below.
- The README is **out of date** (URL prefix, endpoint names).

### Severity legend
🔴 Critical · 🟠 High · 🟡 Medium · 🔵 Low / polish

---

## 2. Test Results — Auth & Registration

| # | Endpoint | Test | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| T1 | `POST /auth/token/` | wrong password | 401 | 401 | ✅ |
| T2 | `POST /auth/token/` | valid credentials | 200 + access/refresh | 200 | ✅ |
| T3 | `POST /auth/token/refresh/` | valid refresh | new access token | 200 | ✅ |
| T4 | `POST /accounts/register/` | new user | 201, OTP emailed | 201 "code sent" | ✅ |
| T5 | `POST /accounts/register/verify/` | wrong OTP | 400 | 400 | ✅ |
| T6 | `POST /accounts/register/verify/` | correct OTP | 200 + JWT pair | 200, user created | ✅ |
| T7 | `POST /auth/token/` | newly registered user logs in | 200 | 200 | ✅ |
| T71 | `POST /auth/token/refresh/` | old refresh reused after rotation | rejected | **still valid** | 🔴 BUG #10 |

**Notes**
- OTP is delivered via **console email backend** (printed in runserver terminal) — fine for dev; SMTP config keys exist but are empty by default.
- There are **no `/accounts/otp/request/` + `/otp/verify/` endpoints** despite the README documenting them. The real flow is `register/` → `register/verify/`.
- `phone_verified` exists on the model but **nothing ever sets it** — no SMS verification exists at all.
- Re-registering with the same email re-sends a fresh OTP (update_or_create) — acceptable "resend" behavior, serializer correctly blocks usernames/emails/phones already used by *existing users*.

---

## 3. Test Results — Catalog

| # | Endpoint | Test | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| T8 | `GET /catalog/medicines/` | unauthenticated read | decide policy | **200 public** | 🟡 note |
| T9 | `POST /catalog/medicines/` | admin creates medicine | 201 | 201 (id=1 Panadol, id=2 Augmentin) | ✅ |
| T10 | `POST /catalog/medicines/` | **customer creates medicine** | 403 | **201 — allowed!** | 🟠 BUG #11 |
| T11 | `GET /catalog/medicines/?q=panadol` | search | only matches | count=1 | ✅ |
| T12 | `GET /catalog/medicines/?requires_prescription=true` | filter | Rx-only meds | count=2 | ✅ |
| T13 | `GET /catalog/categories/`, `/brands/` | list | 200 | 200 (empty) | ✅ |

---

## 4. Test Results — Customer App

| # | Endpoint | Test | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| T15 | `GET /customer/me/` | rider token | 403 | 403 | ✅ role isolation |
| T16 | `GET /customer/me/` | customer | profile auto-created | id=1 | ✅ |
| T17 | `PATCH /customer/me/` | set language / wallet | lang updates; wallet immutable | lang=ur ✓, wallet stays 0 ✓ | ✅ |
| T18–T20 | `/customer/addresses/` | CRUD + ownership | full CRUD | all pass | ✅ |
| T24 | `GET /customer/cart/` | empty cart | 200 | items=[] | ✅ |
| T25–T26 | `POST /customer/cart/` | add items w/ pharmacy_id | items upserted | 2 items | ✅ |
| T27 | `POST /customer/cart/` | **quantity = −5** | 400 validation error | **HTTP 500 IntegrityError (CHECK constraint)** | 🔴 BUG #1 |
| T28 | `POST /customer/cart/` | **medicine_id = 999 (nonexistent)** | 404/400 | **HTTP 500 FK IntegrityError** | 🔴 BUG #2 |
| T29 | `POST /customer/orders/place/` | nonexistent address | 404 | 404 | ✅ |
| T30 | `POST /customer/orders/place/` | qty > stock | 400 "Insufficient stock" | 400 | ✅ |
| T31 | `POST /customer/orders/place/` | happy path (COD) | 201 order | order id=1, total=541.00 ✓ (2×30.50 + 480) | ✅ |
| T32 | DB check after order | stock decremented? | stock reduced | **Panadol still 50, Augmentin still 20** | 🟠 BUG #5 |
| T33 | `GET /customer/cart/` | cart cleared after order | empty | 0 items | ✅ |
| T60 | `POST /customer/prescriptions/` | multipart upload, AI service offline | graceful fallback | status=`needs_review`, file stored, ~4.5 s delay | ✅ (see note) |
| T62 | `POST /customer/prescriptions/<id>/build-cart/` | build cart from Rx | suggested items | **always empty** | 🟠 BUG #7 |

**Notes**
- Prescription upload calls the AI microservice **synchronously inline** (~4.5 s when it's unreachable). Comment in code says Celery would be used in production — Celery is configured in settings but has no tasks/app module at all.
- `ai_raw_response` stayed `null` because nothing listens on `AI_SERVICE_BASE_URL` (localhost:9000) — fallback works, but see BUG #7: even with AI output, **no code parses it into `PrescriptionItem`s**.
- **No validation that a prescription-required medicine needs an actual prescription** — order #1 contained Augmentin (`requires_prescription=true`) with `prescription=null`. 🟠 BUG #6
- Cart POST silently switches the whole cart's pharmacy if `pharmacy_id` is sent again — items from another pharmacy remain in the cart unchecked. 🟡 design gap
- Customers have **no API to discover pharmacies** (list/search pharmacies) — `pharmacy_id` must be known magically. 🟠 missing feature

---

## 5. Test Results — Pharmacy App

| # | Endpoint | Test | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| T21 | `GET /pharmacy/me/` | auto-create profile | verified profile | **license=`TEMP-10`, `is_verified=False`** | 🟡 note |
| T22 | `POST /pharmacy/inventory/` | create stock rows | 201 | 201 (`medicine_id` required on write; nested `medicine` on read) | ✅ |
| T22c | `PATCH /pharmacy/inventory/<id>/` | restock | updated + low_stock flag recalcs | qty=20, low=False | ✅ |
| T22d | `POST /pharmacy/inventory/` | **duplicate row (same medicine)** | 400 unique error | **HTTP 500 IntegrityError** | 🔴 BUG #3 |
| T23 | `POST /pharmacy/inventory/` | customer token | 403 | 403 | ✅ |
| T34 | `GET /pharmacy/orders/incoming/` | list active orders | pending order shown | shown | ✅ |
| T35 | `POST /pharmacy/orders/1/accept/` | transition | accepted | accepted | ✅ |
| T36 | `POST .../accept/` (again) | idempotency guard | 409/400 | **200 again — duplicate history row** | 🟡 BUG #8 |
| T37 | `POST .../preparing/` | transition | preparing | preparing | ✅ |
| T38 | `POST .../bogus-action/` | unknown action | 400 | 400 | ✅ |
| T39 | `POST .../ready-for-pickup/` | triggers rider dispatch | delivery + offers | delivery created, **0 offers (no verified riders)** | 🟡 see §6 |
| T68 | `POST /pharmacy/orders/2/reject/` | reject pending order | cancelled | cancelled | ✅ |
| T69 | `POST /pharmacy/orders/1/reject/` | **reject DELIVERED order** | refused | **delivered+paid order became `cancelled`!** | 🔴 BUG #9 |
| T63 | `POST /pharmacy/prescriptions/1/verify/` | approve | verified | verified | ✅ |
| T64b | same, decision=`bogus` | invalid decision | 400 | 400 | ✅ |
| T65b | customer hits verify endpoint | 403 | 403 | ✅ |
| T66c | **pharm2 verifies cust1's prescription** | 403/404 | **200 — prescription flipped to `rejected` by unrelated pharmacy!** | 🔴 CRITICAL BUG #12 |
| T67 | `GET /pharmacy/forecasts/` | list forecasts | 200 | 200, empty (no writer exists) | ✅ |

**Notes**
- Any pharmacy-role user auto-gets a profile with fake license `TEMP-<user.id>` and `is_verified=False`; **orders can be placed with unverified pharmacies** — verification is never enforced anywhere. 🟠
- `under_review` order status is defined but **never set by any code path** — dead state.
- Prescription→pharmacy relationship doesn't exist in the data model (a prescription isn't "sent to" a specific pharmacy), which is partly why BUG #12 happens.

---

## 6. Test Results — Rider App & Dispatch

Setup: rider profiles default to `is_verified=False`, so first dispatch attempt (T39) produced **zero offers and no assignment — silently**. No retry mechanism, no notification, order stuck at `ready_for_pickup` forever. After verifying riders via Django admin (shell), dispatch worked:

| # | Endpoint | Test | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| T40 | `GET /rider/me/` | auto-create profile | 200 | 200 | ✅ |
| T41 | `PATCH /rider/me/` | coords update; is_verified immutable | ok | ok | ✅ |
| T42 | `POST /rider/location/` | location ping | 201 + profile coords updated | ok | ✅ |
| T43 | re-run `ready-for-pickup` | dispatch retry | offers for riders | 2 offers + auto-assign | ✅ (but see scoring bug) |
| T44 | `GET /rider/offers/` | own offers only | rider1 sees his 1 offer | 1 | ✅ |
| T46 | `POST /rider/offers/2/respond/` | rider1 accepts offer | assignment moves to rider1 | moved (auto-assigned rider2 overridden) | 🟡 design gap |
| T47–T48 | `GET /rider/deliveries/` | stolen job not actionable | rider2 sees nothing / gets 404 | 0 deliveries, 404 | ✅ safe |
| T49 | `POST /rider/deliveries/1/start/` | **start before pickup** | refused | **200 — out-of-order transitions allowed** | 🟠 BUG #13 |
| T50–T52 | confirm-pickup → start → confirm-delivered | lifecycle | timestamps + status | picked_up_at/on_the_way/delivered ✓, COD `is_paid=True` ✓ | ✅ |

**Dispatch logic findings**
- Rider scoring `_score_rider()` = `random.uniform(0,10) − load×5` and ETA = `random.randint(12,18)` — placeholders, clearly flagged in code. But there's an extra bug: the score is computed **once for sorting and again when saving the offer**, so the stored offer score doesn't match the decision (observed: rider1 score 4.12 > rider2 3.23, yet rider2 was auto-assigned). 🟡 BUG #14
- Losing rider's `DeliveryOffer` stays `"offered"` forever (never invalidated/expired); "expired" choice exists but no expiry logic.
- Dispatch failure (no eligible riders) is **silent** — no log, no flag on the Delivery, no re-dispatch trigger. 🟠
- Only fix path today: an admin manually flips `is_verified=True` in Django admin — **there is no API to verify a rider or pharmacy**. 🟠 missing feature

---

## 7. Test Results — Shared Orders API

| # | Endpoint | Test | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| T53 | `GET /orders/` | role-aware listing (customer) | own orders only | 1 own order | ✅ |
| T54 | `GET /orders/1/` | other customer reads | 404 | 404 | ✅ |
| T55 | `GET /orders/` | unauthenticated | 401 | 401 | ✅ |
| T56 | `GET /orders/1/` | tracking detail incl. history | status_history present | 9 entries | ✅ |
| T57 | `POST /orders/1/refund/` | owner requests refund | 201 requested | 201 | ✅ |
| T58 | refund by non-owner | 404 | 404 | ✅ |

**Audit trail check (DB inspection of `OrderStatusHistory`):**
```
accepted         ← initial 'pending' was NEVER recorded (Order created with default status)
accepted         ← duplicate from unguarded re-accept (T36)
preparing
ready_for_pickup
ready_for_pickup ← duplicate from re-dispatch (T43)
on_the_way       ← out-of-order entry from T49 (before pickup!)
picked_up
on_the_way
delivered
```
🟠 Issues: missing initial `pending` entry; duplicates; out-of-order entries possible because `Order.set_status()` accepts any value with no transition rules.

Refund has **no approve/reject endpoint** — refunds stay `requested` forever (only requestable). 🟡

---

## 8. Consolidated Bug List

### 🔴 Critical

| # | Where | Problem |
|---|---|---|
| **B1** | `apps/customer/views.py` `CartView.post` | Negative/zero quantity → unhandled `IntegrityError` (CHECK constraint) → **HTTP 500**. Must validate `quantity >= 1` and return 400. |
| **B2** | `apps/customer/views.py` `CartView.post` | Nonexistent `medicine_id` → FK IntegrityError → **HTTP 500**. Should return 400/404. |
| **B3** | `apps/medical_store` InventoryViewSet | Duplicate inventory row (same pharmacy+medicine) → unique-constraint IntegrityError → **HTTP 500** instead of clean 400. |
| **B9** | `medical_store.views.OrderTransitionView` | **No state guards**: a *delivered* order was flipped to `cancelled` via `reject` (reproduced!). Transitions ignore current status entirely. |
| **B12** | `medical_store.views.VerifyPrescriptionView` | **Cross-pharmacy authorization hole**: lookup is `get_object_or_404(Prescription, id=...)` with no scoping — *any* pharmacy can verify/reject *any* customer's prescription (verified live: pharm2 flipped cust1's approved Rx to rejected), and statuses can be re-flipped repeatedly. |

### 🟠 High

| # | Where | Problem |
|---|---|---|
| **B5** | `customer.services.place_order_from_cart` | Stock is checked but **never decremented** on order placement → overselling guaranteed under concurrency. |
| **B6** | Order placement | `requires_prescription=true` medicines can be ordered **without any prescription attached** — no enforcement at cart/order time. |
| **B7** | Prescription pipeline | Nothing parses `ai_raw_response` into `PrescriptionItem` rows → `build-cart-from-prescription` always yields an **empty cart** unless items are hand-entered in admin. The flagship AI feature is effectively non-functional. |
| **B10** | JWT config | `ROTATE_REFRESH_TOKENS=True` but `rest_framework_simplejwt.token_blacklist` app is **not installed** → rotated-out refresh tokens remain valid until natural expiry (14 days). Token theft window never closes. |
| **B11** | `catalog` ViewSets | Permission is `IsAuthenticatedOrReadOnly` → **any authenticated user (customer/rider!) can create/edit/delete shared medicines, categories, brands** (verified: customer created medicine). Should be admin-only. |
| **B13** | `rider.services` transitions | No sequence enforcement: `start` succeeds before `confirm-pickup`; corrupts audit trail. Same class of bug as B9. |
| — | Dispatch | Silent no-op when zero eligible riders (order stalls forever, no signal/retry). Also **no API to verify riders/pharmacies** — impossible to run the platform through the API alone. |
| — | Customer UX | No endpoint to browse/search pharmacies (needed for `cart.pharmacy_id`). No customer cancel-order endpoint. Refund cannot be approved/rejected. |

### 🟡 Medium / Low

- **B8**: duplicate transitions allowed (accept twice, ready-for-pickup twice → duplicate history rows).
- **B14**: rider offer `score` recomputed randomly at save time — stored scores don't match the ranking decision.
- `under_review` status unreachable; `phone_verified` never set; OTP is email-only while model/UI implies phone.
- Cart allows mixing items across pharmacies (switching `pharmacy_id` keeps old items).
- `DeliveryOffer.expired` choice unused; losing rider's offer stays `offered`.
- Settings defaults unsafe for prod: `DEBUG=True`, `ALLOWED_HOSTS=*`, `CORS_ALLOW_ALL_ORIGINS=True`, hardcoded `SECRET_KEY` fallback, personal email `sussbhoo@gmail.com` as `DEFAULT_FROM_EMAIL` default.
- Celery configured in settings but no celery app/tasks exist; AI extraction runs blocking-inline in the upload request (~4.5 s stall observed).
- README drift: documents `/api/...` prefixed routes and `/api/accounts/otp/request|verify` endpoints that don't exist; trailing UTF-16 junk lines at end of file.
- Repo hygiene: committed `db.sqlite3`, `pip-django-upgrade*.log`, no tests directory.

---

## 9. What Works Correctly ✅

- Registration → email OTP → verify → JWT pair; login/refresh; password validation on register.
- Role isolation between apps (customer/pharmacy/rider endpoints reject foreign roles with 403).
- Ownership scoping everywhere tested (addresses, orders, refunds, prescriptions lists, rider offers/deliveries) — except B12.
- Cart math and order totals (subtotal/delivery/discount/total) compute correctly; cart cleared atomically after order; insufficient-stock returns 400 inside a transaction.
- Pharmacy workflow endpoints and incoming-orders filter; unknown actions rejected with 400.
- Rider location pings persist + update profile coordinates.
- COD auto-marks `is_paid` on delivery confirmation; card payment stays unpaid (as designed).
- Order detail includes full status history; cross-customer access blocked.
- Media uploads served correctly in DEBUG.
- Search/filter/pagination on catalog and list endpoints.

---

## 10. Recommended Fix Priority

1. **B12** — scope prescription verification (e.g., add `prescription.pharmacy` FK or restrict to pharmacies with an order from that customer); block re-decisions after terminal status.
2. **B9/B13** — add a legal-transition map to `Order.set_status()` and enforce it in both transition views; make reject only valid pre-`accepted`; add idempotency guards (B8).
3. **B1/B2/B3** — validate cart quantity (`min_value=1`) and medicine existence; catch unique violations in inventory serializer (`validate()` or `get_or_create`) returning 400.
4. **B5** — decrement `InventoryItem.quantity_in_stock` (with `select_for_update`) inside the order transaction.
5. **B11** — admin-only write permissions for catalog.
6. **B10** — add `"rest_framework_simplejwt.token_blacklist"` to INSTALLED_APPS + migrate.
7. **B7/B6** — implement AI-response → `PrescriptionItem` parsing; enforce prescription requirement at order time.
8. Add: pharmacy browse endpoint, rider/pharmacy verification endpoints (admin), customer cancel, refund decisions, dispatch retry/failure signal.
9. Update README (real URL paths), remove committed db/logs, add automated tests.

---

*Test artifacts: `seed_test_users.py` (test data bootstrap), `server_out.log` / `server_err.log` (dev-server logs), `test_prescription.png` (upload fixture). Dev server left running on 127.0.0.1:8000 during testing.*
