import json
import sqlite3
import sys

import requests

BASE = "http://127.0.0.1:8000"
FAILURES = []


def check(name, cond, extra=""):
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name} {extra}")
    if not cond:
        FAILURES.append(name)


def db_otp(email):
    con = sqlite3.connect("db.sqlite3")
    row = con.execute(
        "SELECT otp_code FROM accounts_pendingregistration WHERE email=?", (email,)
    ).fetchone()
    con.close()
    return row[0] if row else None


def register_and_login(email, username, role, phone):
    r = requests.post(
        f"{BASE}/accounts/register/",
        json={
            "username": username,
            "email": email,
            "password": "Test@12345",
            "role": role,
            "phone_number": phone,
        },
        timeout=30,
    )
    if r.status_code == 201:
        check(f"register {username}", True)
    elif r.status_code == 400 and ("already exist" in r.text or "pending" in r.text):
        print(f"[SKIP] {username} already registered — logging in directly")
    else:
        check(f"register {username}", False, str(r.status_code) + " " + r.text[:120])
        return None
    otp = db_otp(email)
    if not otp:
        r = requests.post(
            f"{BASE}/accounts/login/",
            json={"email": email, "password": "Test@12345"}, timeout=15,
        )
        check(f"login existing user {username}", r.status_code == 200, r.text[:150])
        data = r.json()
        return {"access": data["access"], "refresh": data["refresh"], "user": data["user"]}
    check(f"otp exists for {email}", True)
    r = requests.post(
        f"{BASE}/accounts/register/verify/", json={"email": email, "code": otp}, timeout=30
    )
    if r.status_code != 200:
        r = requests.post(
            f"{BASE}/accounts/login/",
            json={"email": email, "password": "Test@12345"}, timeout=15,
        )
        check(f"login fallback {username}", r.status_code == 200, r.text[:150])
        data = r.json()
        return {"access": data["access"], "refresh": data["refresh"], "user": data["user"]}
    check(f"verify {username}", True)
    data = r.json()
    return {"access": data["access"], "refresh": data["refresh"], "user": data["user"]}


def auth(tok):
    return {"Authorization": "Bearer " + tok}


def main():
    # ---- register 3 roles ----
    ph = register_and_login("e2e.pharm@test.com", "e2epharm", "pharmacy", "+923001111101")
    cu = register_and_login("e2e.cust@test.com", "e2ecust", "customer", "+923001111102")
    rd = register_and_login("e2e.rider@test.com", "e2erider", "rider", "+923001111103")
    if not (ph and cu and rd):
        sys.exit(1)

    H_PH, H_CU, H_RD = auth(ph["access"]), auth(cu["access"]), auth(rd["access"])

    # customer profile bootstrap (the web UI does GET /customer/me/ on entry)
    r = requests.get(f"{BASE}/customer/me/", headers=H_CU, timeout=10)
    check("bootstrap GET /customer/me/", r.status_code == 200, r.text[:120])

    # rider profile bootstrap (same pattern as the web UI's rider dashboard)
    r = requests.get(f"{BASE}/rider/me/", headers=H_RD, timeout=10)
    check("bootstrap GET /rider/me/", r.status_code == 200, r.text[:120])

    # ---- login again (email-based) ----
    r = requests.post(
        f"{BASE}/accounts/login/",
        json={"email": "e2e.pharm@test.com", "password": "Test@12345"},
        timeout=15,
    )
    check("login via /accounts/login/", r.status_code == 200 and "access" in r.json())

    # ---- catalog seed (any authenticated user can write catalog - bug B11) ----
    r = requests.get(f"{BASE}/catalog/categories/", timeout=10).json()
    cats = {c["name"]: c["id"] for c in r["results"]}
    if "Pain Relief" not in cats:
        r = requests.post(
            f"{BASE}/catalog/categories/", headers=H_CU,
            json={"name": "Pain Relief", "description": "test"}, timeout=10,
        )
        cats["Pain Relief"] = r.json()["id"]
    r = requests.get(f"{BASE}/catalog/brands/", timeout=10).json()
    brands = {b["name"]: b["id"] for b in r["results"]}
    if "GSK" not in brands:
        r = requests.post(f"{BASE}/catalog/brands/", headers=H_CU, json={"name": "GSK"}, timeout=10)
        brands["GSK"] = r.json()["id"]

    r = requests.get(f"{BASE}/catalog/medicines/?q=Panadol", timeout=10).json()
    panadol = next((m for m in r["results"] if m["name"] == "Panadol"), None)
    if not panadol:
        r = requests.post(
            f"{BASE}/catalog/medicines/", headers=H_CU,
            json={
                "name": "Panadol", "generic_name": "paracetamol", "strength": "500mg",
                "form": "tablet", "category": cats["Pain Relief"], "brand": brands["GSK"],
                "requires_prescription": False, "description": "E2E test medicine",
                "is_active": True,
            },
            timeout=10,
        )
        check("create Panadol", r.status_code in (200, 201), r.text[:150])
        panadol = r.json()

    # search filter used by the UI (?q=)
    r = requests.get(f"{BASE}/catalog/medicines/?q=panad", timeout=10).json()
    check("medicine search ?q=", any(m["id"] == panadol["id"] for m in r["results"]))

    # ---- pharmacy directory (new endpoint) ----
    r = requests.get(f"{BASE}/pharmacy/directory/", timeout=10)
    check("GET /pharmacy/directory/ public", r.status_code == 200)

    # ---- pharmacy profile + inventory ----
    r = requests.patch(
        f"{BASE}/pharmacy/me/", headers=H_PH,
        json={
            "business_name": "E2E Pharmacy", "address_line": "12 Test Road",
            "city": "Lahore", "is_open": True,
            "latitude": "31.520370", "longitude": "74.358750",
        },
        timeout=10,
    )
    check("PATCH /pharmacy/me/", r.status_code == 200, r.text[:120])
    pharm_profile_id = r.json()["id"]

    r = requests.get(f"{BASE}/pharmacy/inventory/", headers=H_PH, timeout=10).json()
    inv_row = next((i for i in r["results"] if i["medicine"]["id"] == panadol["id"]), None)
    if not inv_row:
        r = requests.post(
            f"{BASE}/pharmacy/inventory/", headers=H_PH,
            json={"medicine_id": panadol["id"], "quantity_in_stock": 100,
                  "reorder_threshold": 10, "selling_price": "45.00"},
            timeout=10,
        )
        check("POST inventory", r.status_code in (200, 201), r.text[:150])
    else:
        print("[SKIP] inventory row already exists")

    r = requests.get(f"{BASE}/pharmacy/directory/", timeout=10).json()
    check("directory lists our pharmacy", any(p["id"] == pharm_profile_id for p in r))

    # ---- customer: address, cart, order ----
    r = requests.post(
        f"{BASE}/customer/addresses/", headers=H_CU,
        json={"label": "Home", "address_line": "42 Test Street", "city": "Lahore", "is_default": True},
        timeout=10,
    )
    check("add address", r.status_code in (200, 201))
    address_id = r.json()["id"]

    r = requests.post(
        f"{BASE}/customer/cart/", headers=H_CU,
        json={"medicine_id": panadol["id"], "quantity": 3, "pharmacy_id": pharm_profile_id},
        timeout=10,
    )
    check("cart add", r.status_code == 200 and len(r.json()["items"]) == 1, r.text[:150])
    cart_item = r.json()["items"][0]
    check("cart line_total computed", float(cart_item["line_total"]) == 135.0, str(cart_item["line_total"]))

    r = requests.post(
        f"{BASE}/customer/orders/place/", headers=H_CU,
        json={"address_id": address_id, "payment_method": "cod"}, timeout=15,
    )
    check("place order", r.status_code == 201, r.text[:200])
    order = r.json()
    oid = order["id"]
    check("order total", float(order["total"]) == 135.0, str(order["total"]))

    # cart cleared?
    r = requests.get(f"{BASE}/customer/cart/", headers=H_CU, timeout=10).json()
    check("cart cleared after order", len(r["items"]) == 0)

    # ---- order lifecycle: customer sees it ----
    r = requests.get(f"{BASE}/orders/{oid}/", headers=H_CU, timeout=10)
    check("order detail (customer)", r.status_code == 200 and r.json()["status"] == "pending")

    # ---- pharmacy transitions ----
    r = requests.get(f"{BASE}/pharmacy/orders/incoming/", headers=H_PH, timeout=10).json()
    check("incoming orders shows order", any(o["id"] == oid for o in r["results"]))

    for action, expected in [("accept", "accepted"), ("preparing", "preparing"), ("ready-for-pickup", "ready_for_pickup")]:
        r = requests.post(f"{BASE}/pharmacy/orders/{oid}/{action}/", headers=H_PH, timeout=10)
        check(f"pharmacy {action}", r.status_code == 200 and r.json()["status"] == expected, r.text[:120])

    # rider must be verified for dispatch? flip is_verified directly in DB like admin would
    con = sqlite3.connect("db.sqlite3")
    tables = [t[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    rider_table = next(t for t in tables if t.endswith("riderprofile"))
    cur = con.execute(
        f"UPDATE {rider_table} SET is_verified=1, is_available=1 "
        "WHERE user_id=(SELECT id FROM accounts_user WHERE username='e2erider')"
    )
    con.commit()
    check("flip rider is_verified in DB", cur.rowcount == 1, f"table={rider_table}")
    con.close()

    # dispatch already ran at ready-for-pickup; re-trigger to create offers now that rider verified
    r = requests.post(f"{BASE}/pharmacy/orders/{oid}/ready-for-pickup/", headers=H_PH, timeout=10)
    check("re-trigger ready-for-pickup for dispatch", r.status_code == 200)

    # ---- rider flow ----
    r = requests.get(f"{BASE}/rider/offers/", headers=H_RD, timeout=10).json()
    offers = r["results"]
    check("rider has offer(s)", len(offers) >= 1, f"n={len(offers)}")
    if offers:
        offer_id = offers[0]["id"]
        r = requests.post(
            f"{BASE}/rider/offers/{offer_id}/respond/", headers=H_RD,
            json={"decision": "accepted"}, timeout=10,
        )
        check("accept offer", r.status_code == 200)

        r = requests.get(f"{BASE}/rider/deliveries/", headers=H_RD, timeout=10).json()
        check("delivery assigned", len(r["results"]) >= 1)
        delivery_order = r["results"][0]["order"]
        check("delivery points at our order", delivery_order == oid)

        for action in ["confirm-pickup", "start", "confirm-delivered"]:
            r = requests.post(f"{BASE}/rider/deliveries/{oid}/{action}/", headers=H_RD, timeout=10)
            check(f"rider {action}", r.status_code == 200, r.text[:120])

    # location ping
    r = requests.post(
        f"{BASE}/rider/location/", headers=H_RD,
        json={"latitude": "31.5204", "longitude": "74.3587"}, timeout=10,
    )
    check("rider location ping", r.status_code == 201)

    # ---- final state ----
    r = requests.get(f"{BASE}/orders/{oid}/", headers=H_CU, timeout=10).json()
    check("order delivered", r["status"] == "delivered", r["status"])
    check("cod auto-paid on delivery", r["is_paid"] is True)
    check("status history recorded", len(r["status_history"]) >= 6, str(len(r["status_history"])))
    check("delivery embedded with eta", bool(r["delivery"]), "")

    # refund request
    r = requests.post(
        f"{BASE}/orders/{oid}/refund/", headers=H_CU,
        json={"amount": "50.00", "reason": "e2e test refund"}, timeout=10,
    )
    check("refund requested", r.status_code == 201)

    print("\n" + ("ALL PASSED" if not FAILURES else f"FAILURES: {FAILURES}"))
    sys.exit(0 if not FAILURES else 1)


if __name__ == "__main__":
    main()
