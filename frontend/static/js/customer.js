const Customer = (() => {
  const PAGE_SIZE = 20;
  let shopState = { page: 1, q: "", category: "", rx: "", meds: [], categories: [] };
  const PAYMENT_METHODS = [
    ["cod", "Cash on Delivery"],
    ["card", "Card"],
    ["jazzcash", "JazzCash"],
    ["easypaisa", "Easypaisa"],
    ["wallet", "Wallet"],
  ];

  let profileReady = null;
  function ensureProfile() {
    if (!profileReady) {
      profileReady = API.get("/customer/me/").catch((err) => { profileReady = null; throw err; });
    }
    return profileReady;
  }

  // ---------- Pharmacy picker ----------
  async function pickPharmacy(force = false) {
    if (!force) {
      const saved = localStorage.getItem("mp_cart_pharmacy");
      if (saved) return JSON.parse(saved);
    }
    return await openPharmacyPicker();
  }

  function openPharmacyPicker() {
    return new Promise((resolve) => {
      UI.modal(`<h3>Choose a pharmacy</h3><div id="ph-list">${UI.loading()}</div>`, async (backdrop, close) => {
        try {
          const { results } = API.unwrap(await API.get("/pharmacy/directory/"));
          if (!results.length) {
            backdrop.querySelector("#ph-list").innerHTML = UI.emptyState("No pharmacies yet", "Register a pharmacy account and add its shop first.");
            return;
          }
          backdrop.querySelector("#ph-list").innerHTML = results
            .map(
              (p) => `
              <div class="order-card" style="cursor:pointer;margin-bottom:10px" data-ph="${p.id}">
                <div class="oc-head">
                  <span class="oc-id">${UI.esc(p.business_name)}</span>
                  ${p.is_verified ? '<span class="badge green">Verified</span>' : '<span class="badge gray">Unverified</span>'}
                  <span class="oc-date" style="flex:1;text-align:right">${UI.esc(p.city || "")}</span>
                </div>
                <div class="hint">${UI.esc(p.address_line || "")}</div>
              </div>`
            )
            .join("");
          backdrop.querySelectorAll("[data-ph]").forEach((el) => {
            el.onclick = () => {
              const ph = results.find((p) => p.id === Number(el.dataset.ph));
              localStorage.setItem("mp_cart_pharmacy", JSON.stringify(ph));
              close();
              resolve(ph);
            };
          });
        } catch (err) {
          backdrop.querySelector("#ph-list").innerHTML = `<div class="banner error">${UI.errText(err)}</div>`;
        }
      });
    });
  }

  async function ensureCartPharmacy() {
    let ph = null;
    const saved = localStorage.getItem("mp_cart_pharmacy");
    if (saved) ph = JSON.parse(saved);
    if (!ph) ph = await openPharmacyPicker();
    return ph;
  }

  // ---------- Shop ----------
  async function renderShop(container) {
    await ensureProfile();
    container.innerHTML = `
      <div class="page-header">
        <div><h2>Medicine Store</h2><div class="desc">Browse the verified catalog and add medicines to your cart.</div></div>
        <button class="btn secondary sm" id="switch-ph">Change Pharmacy</button>
      </div>
      <div id="shop-ph-bar"></div>
      <div class="toolbar">
        <input class="input search" id="shop-q" placeholder="Search medicine or generic name..." value="${UI.esc(shopState.q)}" />
        <select class="input" id="shop-cat"><option value="">All categories</option></select>
        <select class="input" id="shop-rx">
          <option value="">All items</option>
          <option value="false">OTC only</option>
          <option value="true">Prescription only</option>
        </select>
        <button class="btn" id="shop-search">Search</button>
      </div>
      <div id="shop-results"></div>`;

    const catSel = document.getElementById("shop-cat");
    const rxSel = document.getElementById("shop-rx");
    rxSel.value = shopState.rx;

    const [catData, ph] = await Promise.all([
      API.unwrap(API.get("/catalog/categories/")),
      currentCartPharmacy(),
    ]);
    shopState.categories = catData.results || [];
    shopState.categories.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.name;
      if (String(c.id) === String(shopState.category)) opt.selected = true;
      catSel.appendChild(opt);
    });

    renderPhBar(ph);
    document.getElementById("switch-ph").onclick = async () => {
      const newPh = await openPharmacyPicker();
      renderPhBar(newPh);
    };

    const doSearch = (page = 1) => {
      shopState.page = page;
      shopState.q = document.getElementById("shop-q").value.trim();
      shopState.category = catSel.value;
      shopState.rx = rxSel.value;
      loadMeds();
    };
    document.getElementById("shop-search").onclick = () => doSearch(1);
    document.getElementById("shop-q").addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(1); });
    catSel.onchange = () => doSearch(1);
    rxSel.onchange = () => doSearch(1);

    await loadMeds();
  }

  async function currentCartPharmacy() {
    const saved = localStorage.getItem("mp_cart_pharmacy");
    if (saved) return JSON.parse(saved);
    try {
      const cart = await API.get("/customer/cart/");
      if (cart.pharmacy) {
        localStorage.setItem("mp_cart_pharmacy", JSON.stringify(cart.pharmacy));
        return cart.pharmacy;
      }
    } catch {}
    return null;
  }

  function renderPhBar(ph) {
    document.getElementById("shop-ph-bar").innerHTML = ph
      ? `<div class="banner info" style="display:flex;align-items:center;gap:10px">
           Shopping from <b>&nbsp;${UI.esc(ph.business_name)}</b>&nbsp;(${UI.esc(ph.city || "—")})
         </div>`
      : `<div class="banner warn">No pharmacy selected — you will be asked to pick one when adding to cart.</div>`;
  }

  async function loadMeds() {
    const box = document.getElementById("shop-results");
    await UI.withLoading(box, async () => {
      const params = new URLSearchParams({ page: shopState.page });
      if (shopState.q) params.set("q", shopState.q);
      if (shopState.category) params.set("category", shopState.category);
      if (shopState.rx) params.set("requires_prescription", shopState.rx);
      const data = API.unwrap(await API.get(`/catalog/medicines/?${params}`));
      const pharmacy = await currentCartPharmacy();
      const inventoryData = pharmacy
        ? API.unwrap(await API.get(`/pharmacy/${pharmacy.id}/inventory/`))
        : { results: [] };
      const inventoryByMedicine = new Map(inventoryData.results.map((item) => [item.medicine.id, item]));
      shopState.meds = data.results;
      if (!data.results.length) {
        box.innerHTML = UI.emptyState("No medicines found", "Try a different search, or seed demo data from Test Utilities.");
        return;
      }
      box.innerHTML = `
        <div class="med-grid">
          ${data.results.map((medicine) => medCard(medicine, inventoryByMedicine.get(medicine.id))).join("")}
        </div>
        ${UI.pager(shopState.page, data.count, PAGE_SIZE, (p) => { shopState.page = p; loadMeds(); })}`;
      box.querySelectorAll("[data-add]").forEach((btn) => {
        btn.onclick = () => addToCart(Number(btn.dataset.add), Number(btn.closest(".add-row").querySelector(".qty-input").value));
      });
    });
  }

  function medCard(m, inventory) {
    const available = inventory && inventory.quantity_in_stock > 0;
    const discountedPrice = inventory
      ? Number(inventory.selling_price) * (1 - Number(inventory.discount_percentage || 0) / 100)
      : 0;
    return `
      <div class="card med-card">
        <div class="med-tags">
          ${m.requires_prescription ? '<span class="rx-badge">Rx REQUIRED</span>' : '<span class="badge teal">OTC</span>'}
          ${m.form ? `<span class="tag">${UI.esc(m.form)}</span>` : ""}
          ${m.strength ? `<span class="tag">${UI.esc(m.strength)}</span>` : ""}
        </div>
        <div>
          <div class="med-name">${UI.esc(m.name)}</div>
          <div class="med-generic">${UI.esc(m.generic_name || "")}${m.brand ? " · " + UI.esc(m.brand.name) : ""}</div>
        </div>
        <div class="med-price">${available ? `${UI.money(discountedPrice)}${inventory.discount_percentage > 0 ? ` <span class="hint">(${inventory.discount_percentage}% off)</span>` : ""}` : "Not available at this pharmacy"}</div>
        ${m.description ? `<div class="hint" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">${UI.esc(m.description)}</div>` : ""}
        <div class="med-foot">
          <span class="hint">#${m.id}</span>
          <div class="add-row">
            <input type="number" class="input qty-input" min="1" value="1" />
            <button class="btn sm" data-add="${m.id}" ${available ? "" : "disabled"}>${available ? "Add to Cart" : "Unavailable"}</button>
          </div>
        </div>
      </div>`;
  }

  async function addToCart(medicineId, quantity) {
    if (!quantity || quantity < 1) { UI.toast("Quantity must be at least 1", "error"); return; }
    try {
      await ensureProfile();
      const ph = await ensureCartPharmacy();
      if (!ph) return;
      await API.post("/customer/cart/", { medicine_id: medicineId, quantity, pharmacy_id: ph.id });
      UI.toast(`Added to cart (${quantity} pcs)`, "success");
      App.refreshCartBadge();
    } catch (err) {
      UI.toastErr(err);
    }
  }

  // ---------- Cart ----------
  async function renderCart(container) {
    await ensureProfile();
    await UI.withLoading(container, async () => {
      const cart = await API.get("/customer/cart/");
      const items = (cart.items || []).filter((i) => i.quantity > 0);
      const subtotal = items.reduce((s, i) => s + Number(i.line_total || 0), 0);
      container.innerHTML = `
        <div class="page-header">
          <div><h2>Your Cart</h2><div class="desc">${cart.pharmacy ? "Pharmacy: " + UI.esc(cart.pharmacy.business_name) : "No pharmacy selected yet"}</div></div>
          <button class="btn secondary sm" id="cart-switch-ph">${cart.pharmacy ? "Switch Pharmacy" : "Select Pharmacy"}</button>
        </div>
        <div class="grid cols-2">
          <div class="card">
            <div class="card-title">Items (${items.length})</div>
            ${items.length === 0
              ? UI.emptyState("Cart is empty", "Browse the store and add some medicines.")
              : items.map(cartLine).join("")}
          </div>
          <div>
            <div class="card">
              <div class="card-title">Summary</div>
              <div class="summary-row"><span>Subtotal</span><b>${UI.money(subtotal)}</b></div>
              <div class="summary-row"><span>Delivery fee</span><span class="hint">set by backend at placement</span></div>
              <div class="summary-row total"><span>Total (est.)</span><span>${UI.money(subtotal)}</span></div>
              <button class="btn block" id="go-checkout" ${items.length === 0 || !cart.pharmacy ? "disabled" : ""}>Proceed to Checkout</button>
            </div>
            <div class="card" style="margin-top:14px">
              <div class="hint">
                Note: unit prices are taken from the selected pharmacy's inventory at order placement.
                Items without inventory at that pharmacy get Rs 0 price.
              </div>
            </div>
          </div>
        </div>`;

      container.querySelectorAll("[data-inc]").forEach((b) => b.onclick = () => updateQty(Number(b.dataset.inc), 1));
      container.querySelectorAll("[data-dec]").forEach((b) => b.onclick = async () => {
        const itemId = Number(b.dataset.dec);
        const item = items.find((i) => i.id === itemId);
        if (item.quantity <= 1) {
          const ok = await UI.confirmModal("Remove item?", `${item.medicine.name} will be set to quantity 0 (the API has no hard delete).`, "Remove", true);
          if (!ok) return;
          await updateQty(itemId, -item.quantity);
        } else updateQty(itemId, -1);
      });

      const switchBtn = document.getElementById("cart-switch-ph");
      if (switchBtn) switchBtn.onclick = async () => {
        const ph = await openPharmacyPicker();
        if (ph && cart.pharmacy && ph.id !== cart.pharmacy.id && (cart.items || []).length) {
          UI.toast("Pharmacy switched — existing items stay but stock/prices belong to the new pharmacy.", "");
        }
        renderCart(container);
      };

      const co = document.getElementById("go-checkout");
      if (co) co.onclick = () => (location.hash = "#/checkout");
    });
  }

  function cartLine(i) {
    return `
      <div class="cart-line">
        <div class="info">
          <div class="name">${UI.esc(i.medicine.name)} ${i.medicine.strength ? UI.esc(i.medicine.strength) : ""}</div>
          <div class="sub">#${i.medicine.id} · qty ${i.quantity}</div>
        </div>
        <div class="stepper">
          <button data-dec="${i.id}">−</button>
          <span class="qty">${i.quantity}</span>
          <button data-inc="${i.id}">+</button>
        </div>
        <b style="min-width:80px;text-align:right">${UI.money(i.line_total)}</b>
      </div>`;
  }

  async function updateQty(medicineId, delta) {
    const cart = await API.get("/customer/cart/");
    const item = (cart.items || []).find((i) => i.id === medicineId);
    if (!item) return;
    const newQty = item.quantity + delta;
    try {
      await API.post("/customer/cart/", { medicine_id: item.medicine_id ?? item.medicine.id, quantity: Math.max(0, newQty) });
      renderCart(document.getElementById("view"));
      App.refreshCartBadge();
    } catch (err) {
      UI.toastErr(err);
    }
  }

  // ---------- Checkout ----------
  async function renderCheckout(container) {
    await ensureProfile();
    await UI.withLoading(container, async () => {
      const [cart, addrData] = await Promise.all([
        API.get("/customer/cart/"),
        API.unwrap(API.get("/customer/addresses/")),
      ]);
      const items = (cart.items || []).filter((i) => i.quantity > 0);
      if (!items.length) { location.hash = "#/cart"; return; }
      const subtotal = items.reduce((s, i) => s + Number(i.line_total || 0), 0);

      container.innerHTML = `
        <div class="page-header"><div><h2>Checkout</h2><div class="desc">Order # will be placed with ${UI.esc(cart.pharmacy ? cart.pharmacy.business_name : "—")}</div></div></div>
        <div class="grid cols-2">
          <div class="card">
            <div class="card-title">Delivery address</div>
            <div id="addr-list">
              ${addrData.results.length === 0 ? "<p class='hint'>No addresses yet — add one.</p>" : ""}
              ${addrData.results.map((a, idx) => `
                <label class="order-card" style="display:flex;gap:10px;align-items:flex-start;cursor:pointer;margin-bottom:10px">
                  <input type="radio" name="addr" value="${a.id}" ${idx === 0 || a.is_default ? "checked" : ""} style="margin-top:3px" />
                  <div>
                    <b>${UI.esc(a.label)}</b> ${a.is_default ? '<span class="badge teal">Default</span>' : ""}
                    <div class="hint">${UI.esc(a.address_line)}, ${UI.esc(a.city)}</div>
                  </div>
                </label>`).join("")}
            </div>
            <details>
              <summary style="cursor:pointer;font-size:13.5px;font-weight:600;color:var(--primary-dark)">+ Add new address</summary>
              <form id="new-addr-form" style="margin-top:12px">
                <div class="form-row">
                  <div class="field"><label>Label</label><input class="input" name="label" placeholder="Home" /></div>
                  <div class="field"><label>City</label><input class="input" name="city" required /></div>
                </div>
                <div class="field"><label>Address line</label><input class="input" name="address_line" required /></div>
                <div class="form-row">
                  <div class="field"><label>Latitude</label><input class="input" name="latitude" placeholder="optional" /></div>
                  <div class="field"><label>Longitude</label><input class="input" name="longitude" placeholder="optional" /></div>
                </div>
                <label class="checkbox-row"><input type="checkbox" name="is_default" /> Set as default</label>
                <button class="btn sm secondary" style="margin-top:10px" type="submit">Save Address</button>
              </form>
            </details>
          </div>
          <div class="card">
            <div class="card-title">Payment &amp; review</div>
            <div class="field"><label>Payment method</label>
              <select class="input" id="pay-method">
                ${PAYMENT_METHODS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}
              </select>
            </div>
            <div class="divider"></div>
            ${items.map((i) => `<div class="summary-row"><span>${UI.esc(i.medicine.name)} × ${i.quantity}</span><span>${UI.money(i.line_total)}</span></div>`).join("")}
            <div class="summary-row total"><span>Subtotal</span><span>${UI.money(subtotal)}</span></div>
            <button class="btn block" id="place-order" style="margin-top:14px">Place Order</button>
            <p class="hint" style="margin-top:8px">Stock is checked at the chosen pharmacy when placing. Do not double-click.</p>
          </div>
        </div>`;

      document.getElementById("new-addr-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = e.target;
        try {
          await API.post("/customer/addresses/", {
            label: f.label.value.trim() || "Home",
            address_line: f.address_line.value.trim(),
            city: f.city.value.trim(),
            latitude: f.latitude.value || null,
            longitude: f.longitude.value || null,
            is_default: f.is_default.checked,
          });
          UI.toast("Address saved", "success");
          renderCheckout(container);
        } catch (err) { UI.toastErr(err); }
      });

      document.getElementById("place-order").onclick = async (e) => {
        const btn = e.target;
        const addrId = document.querySelector('input[name="addr"]:checked');
        if (!addrId) { UI.toast("Select a delivery address first", "error"); return; }
        btn.disabled = true;
        btn.textContent = "Placing order...";
        try {
          const order = await API.post("/customer/orders/place/", {
            address_id: Number(addrId.value),
            payment_method: document.getElementById("pay-method").value,
          });
          UI.toast(`Order #${order.id} placed!`, "success");
          location.hash = `#/orders/${order.id}`;
        } catch (err) {
          btn.disabled = false;
          btn.textContent = "Place Order";
          UI.toastErr(err);
        }
      };
    });
  }

  // ---------- Orders ----------
  async function renderOrders(container) {
    await UI.withLoading(container, async () => {
      const data = API.unwrap(await API.get("/orders/"));
      container.innerHTML = `
        <div class="page-header"><div><h2>My Orders</h2><div class="desc">Live status straight from /orders/.</div></div></div>
        ${data.results.length === 0
          ? UI.emptyState("No orders yet", "Place an order from the store.")
          : data.results.map(orderCard).join("")}
        ${UI.pager(1, data.count, PAGE_SIZE, () => {})}`;
      container.querySelectorAll("[data-open-order]").forEach((el) => {
        el.onclick = () => (location.hash = `#/orders/${el.dataset.openOrder}`);
      });
    });
  }

  function orderCard(o) {
    const itemCount = (o.items || []).length;
    return `
      <div class="order-card" data-open-order="${o.id}" style="cursor:pointer">
        <div class="oc-head">
          <span class="oc-id">Order #${o.id}</span>
          ${UI.statusBadge(o.status)}
          ${o.is_paid ? '<span class="badge green">Paid</span>' : '<span class="badge amber">Unpaid</span>'}
          <span class="oc-date">${UI.fmtDate(o.created_at)}</span>
        </div>
        <div class="oc-body">
          <span>${itemCount} item(s) · ${UI.money(o.total)}</span>
          <span>${UI.esc(PAYMENT_METHODS.find(([v]) => v === o.payment_method)?.[1] || o.payment_method)}</span>
          <span>${o.pharmacy ? UI.esc(o.pharmacy.business_name) : ""}</span>
        </div>
      </div>`;
  }

  async function renderOrderDetail(container, orderId, pollHandle) {
    await UI.withLoading(container, async () => {
      const o = await API.get(`/orders/${orderId}/`);
      const active = !["delivered", "cancelled"].includes(o.status);
      const history = o.status_history || [];
      const delivery = o.delivery;

      container.innerHTML = `
        <div class="page-header">
          <div><h2>Order #${o.id} ${UI.statusBadge(o.status)}</h2>
          <div class="desc">Placed ${UI.fmtDate(o.created_at)} · auto-refreshes every 5s while active</div></div>
          <button class="btn secondary sm" onclick="location.hash='#/orders'">Back to orders</button>
        </div>
        <div class="grid cols-2">
          <div>
            <div class="card">
              <div class="card-title">Tracking</div>
              <ul class="timeline">
                ${history.map((h, idx) => `
                  <li class="${idx === history.length - 1 ? "current" : ""}">
                    <span class="tl-dot"></span>
                    <div>
                      <div class="tl-status">${UI.esc(UI.STATUS_LABEL(h.status))}</div>
                      <div class="tl-meta">${UI.fmtDate(h.created_at)}${h.note ? " · " + UI.esc(h.note) : ""}</div>
                    </div>
                  </li>`).join("")}
              </ul>
              ${delivery ? `
                <div class="divider"></div>
                <div class="kv"><span class="k">Rider assigned</span><span class="v">${delivery.rider ? "Yes" : "Not yet"}</span></div>
                ${delivery.rider ? `<div class="kv"><span class="k">ETA window</span><span class="v">${delivery.eta_minutes_min ?? "?"}–${delivery.eta_minutes_max ?? "?"} min</span></div>` : ""}
                ${delivery.picked_up_at ? `<div class="kv"><span class="k">Picked up</span><span class="v">${UI.fmtDate(delivery.picked_up_at)}</span></div>` : ""}
                ${delivery.delivered_at ? `<div class="kv"><span class="k">Delivered</span><span class="v">${UI.fmtDate(delivery.delivered_at)}</span></div>` : ""}
              ` : `<p class="hint">No delivery record yet.</p>`}
            </div>
            <div class="card">
              <div class="card-title">Details</div>
              <div class="kv"><span class="k">Payment</span><span class="v">${UI.esc(o.payment_method)} · ${o.is_paid ? "paid" : "unpaid"}</span></div>
              <div class="kv"><span class="k">Subtotal</span><span class="v">${UI.money(o.subtotal)}</span></div>
              <div class="kv"><span class="k">Delivery fee</span><span class="v">${UI.money(o.delivery_fee)}</span></div>
              <div class="kv"><span class="k">Discount</span><span class="v">${UI.money(o.discount)}</span></div>
              <div class="kv"><span class="k">Total</span><span class="v"><b>${UI.money(o.total)}</b></span></div>
              ${o.delivery_address ? `<div class="kv"><span class="k">Address</span><span class="v">${UI.esc(o.delivery_address.address_line)}, ${UI.esc(o.delivery_address.city)}</span></div>` : ""}
              ${o.coupon_code ? `<div class="kv"><span class="k">Coupon</span><span class="v">${UI.esc(o.coupon_code)}</span></div>` : ""}
            </div>
          </div>
          <div>
            <div class="card">
              <div class="card-title">Items</div>
              ${(o.items || []).map((i) => `
                <div class="cart-line">
                  <div class="info">
                    <div class="name">${UI.esc(i.medicine.name)}</div>
                    <div class="sub">qty ${i.quantity} × ${UI.money(i.unit_price)}</div>
                  </div>
                  <b>${UI.money(i.line_total)}</b>
                </div>`).join("")}
            </div>
            <div class="card">
              <div class="card-title">Refund</div>
              <form id="refund-form" class="inline-form">
                <div class="field"><label>Amount</label><input class="input" name="amount" type="number" step="0.01" value="${Number(o.total)}" required /></div>
                <div class="field" style="flex:1"><label>Reason</label><input class="input" name="reason" placeholder="Why?" required /></div>
                <button class="btn secondary" type="submit">Request Refund</button>
              </form>
              <p class="hint" style="margin-top:8px">Refunds are recorded with status "requested" — no approval endpoint exists in the backend yet.</p>
            </div>
            <div class="card">
              <div class="card-title">Raw JSON</div>
              <details><summary style="cursor:pointer;font-size:13px">View API response</summary>
                <pre class="code" style="margin-top:10px">${UI.esc(JSON.stringify(o, null, 2))}</pre>
              </details>
            </div>
          </div>
        </div>`;

      document.getElementById("refund-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = e.target;
        try {
          await API.post(`/orders/${o.id}/refund/`, { amount: f.amount.value, reason: f.reason.value.trim() });
          UI.toast("Refund requested", "success");
        } catch (err) { UI.toastErr(err); }
      });

      if (active && pollHandle) {
        clearTimeout(pollHandle.t);
        pollHandle.t = setTimeout(() => {
          if (location.hash === `#/orders/${orderId}`) renderOrderDetail(container, orderId, pollHandle);
        }, 5000);
      }
    });
  }

  // ---------- Prescriptions ----------
  async function renderPrescriptions(container) {
    await ensureProfile();
    await UI.withLoading(container, async () => {
      const data = API.unwrap(await API.get("/customer/prescriptions/"));
      const RX_STATUS = {
        uploaded: ["Uploaded", "gray"], processing: ["AI Processing", "amber"],
        needs_review: ["Needs Pharmacist Review", "amber"], verified: ["Verified", "green"],
        rejected: ["Rejected", "red"],
      };
      container.innerHTML = `
        <div class="page-header"><div><h2>Prescriptions</h2><div class="desc">Upload a prescription image/PDF — the AI service extracts items (falls back gracefully when offline).</div></div></div>
        <div class="banner info">Upload calls the AI microservice at localhost:9000 inline (~4.5s timeout). Without AI running, the prescription lands in <b>needs_review</b> for manual pharmacist verification.</div>
        <div class="card">
          <div class="card-title">New prescription</div>
          <form id="rx-form">
            <div class="form-row">
              <div class="field"><label>File (image/PDF)</label><input class="input" type="file" name="file" accept="image/*,.pdf" required /></div>
              <div class="field"><label>Source</label>
                <select class="input" name="source"><option value="camera">Camera</option><option value="gallery">Gallery</option><option value="pdf">PDF</option></select>
              </div>
            </div>
            <div class="form-row">
              <div class="field"><label>Doctor name</label><input class="input" name="doctor_name" /></div>
              <div class="field"><label>Patient name</label><input class="input" name="patient_name" /></div>
            </div>
            <button class="btn" type="submit">Upload Prescription</button>
          </form>
        </div>
        <div class="card">
          <div class="card-title">History (${data.results.length})</div>
          ${data.results.length === 0 ? UI.emptyState("Nothing here", "Upload your first prescription above.") :
          data.results.map((p) => {
            const [lbl, color] = RX_STATUS[p.status] || [p.status, "gray"];
            return `
              <div class="order-card">
                <div class="oc-head">
                  <span class="oc-id">Rx #${p.id}</span>
                  <span class="badge ${color}">${lbl}</span>
                  <span class="oc-date">${UI.fmtDate(p.created_at)}</span>
                </div>
                <div class="oc-body">
                  <span>Dr. ${UI.esc(p.doctor_name || "—")} · Patient: ${UI.esc(p.patient_name || "—")}</span>
                  <span>${(p.items || []).length} extracted item(s)</span>
                </div>
                ${p.file ? `<div style="margin-top:8px"><a href="${UI.mediaUrl(p.file)}" target="_blank" class="mono">View file</a></div>` : ""}
                ${(p.items || []).length ? `
                  <div class="table-wrap" style="margin-top:10px">
                    <table class="table">
                      <tr><th>Raw text</th><th>Matched</th><th>Dosage</th><th>Qty</th><th>Confidence</th><th>Confirmed</th></tr>
                      ${p.items.map((it) => `
                        <tr>
                          <td>${UI.esc(it.raw_medicine_text)}</td>
                          <td>${it.medicine ? UI.esc(it.medicine.name) : '<span class="badge red">unmatched</span>'}</td>
                          <td>${UI.esc(it.dosage || "—")}</td>
                          <td>${it.quantity ?? "—"}</td>
                          <td>${it.confidence != null ? Math.round(it.confidence * 100) + "%" : "—"}</td>
                          <td>${it.pharmacist_confirmed ? "Yes" : "No"}</td>
                        </tr>`).join("")}
                    </table>
                  </div>` : ""}
                <div class="btn-group" style="margin-top:10px">
                  <button class="btn sm secondary" data-build-cart="${p.id}">Build cart from this Rx</button>
                  ${p.ai_raw_response ? `<button class="btn sm ghost" data-show-json='${UI.esc(JSON.stringify(p.ai_raw_response))}'>View AI extraction</button>` : ""}
                </div>
              </div>`;
          }).join("")}
        </div>`;

      document.getElementById("rx-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = e.target;
        if (!f.file.files.length) { UI.toast("Choose a file first", "error"); return; }
        const btn = f.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.textContent = "Uploading + AI extract...";
        const fd = new FormData();
        fd.append("file", f.file.files[0]);
        fd.append("source", f.source.value);
        fd.append("doctor_name", f.doctor_name.value.trim());
        fd.append("patient_name", f.patient_name.value.trim());
        try {
          await API.upload("/customer/prescriptions/", fd);
          UI.toast("Uploaded — check status below", "success");
          renderPrescriptions(container);
        } catch (err) {
          btn.disabled = false;
          btn.textContent = "Upload Prescription";
          UI.toastErr(err);
        }
      });

      container.querySelectorAll("[data-build-cart]").forEach((b) => b.onclick = async () => {
        try {
          await API.post(`/customer/prescriptions/${b.dataset.buildCart}/build-cart/`);
          const cart = await API.get("/customer/cart/");
          UI.toast(`Cart rebuilt — ${(cart.items || []).length} item(s)`, "success");
          App.refreshCartBadge();
        } catch (err) { UI.toastErr(err); }
      });

      container.querySelectorAll("[data-show-json]").forEach((b) => b.onclick = () => {
        UI.modal(`<h3>AI extraction payload</h3><pre class="code">${UI.esc(b.dataset.showJson)}</pre>`);
      });
    });
  }

  // ---------- Addresses ----------
  async function renderAddresses(container) {
    await ensureProfile();
    await UI.withLoading(container, async () => {
      const { results } = API.unwrap(await API.get("/customer/addresses/"));
      container.innerHTML = `
        <div class="page-header"><div><h2>Saved Addresses</h2><div class="desc">Used at checkout for delivery.</div></div></div>
        <div class="grid cols-2">
          <div class="card">
            <div class="card-title">Your addresses</div>
            ${results.length === 0 ? UI.emptyState("None saved", "Add one on the right.") :
              results.map((a) => `
                <div class="order-card">
                  <div class="oc-head">
                    <span class="oc-id">${UI.esc(a.label)}</span>
                    ${a.is_default ? '<span class="badge teal">Default</span>' : ""}
                    <span class="oc-date" style="text-align:right"><button class="link-btn" data-del-addr="${a.id}">Delete</button></span>
                  </div>
                  <div class="hint">${UI.esc(a.address_line)}, ${UI.esc(a.city)}
                    ${a.latitude ? ` · ${Number(a.latitude).toFixed(4)}, ${Number(a.longitude).toFixed(4)}` : ""}</div>
                </div>`).join("")}
          </div>
          <div class="card">
            <div class="card-title">Add address</div>
            <form id="addr-form">
              <div class="field"><label>Label</label><input class="input" name="label" placeholder="Home / Office" /></div>
              <div class="field"><label>Address line</label><input class="input" name="address_line" required /></div>
              <div class="field"><label>City</label><input class="input" name="city" required /></div>
              <div class="form-row">
                <div class="field"><label>Latitude</label><input class="input" name="latitude" placeholder="optional" /></div>
                <div class="field"><label>Longitude</label><input class="input" name="longitude" placeholder="optional" /></div>
              </div>
              <label class="checkbox-row"><input type="checkbox" name="is_default" /> Set as default</label>
              <button class="btn" style="margin-top:12px" type="submit">Save</button>
            </form>
          </div>
        </div>`;

      document.getElementById("addr-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = e.target;
        try {
          await API.post("/customer/addresses/", {
            label: f.label.value.trim() || "Home",
            address_line: f.address_line.value.trim(),
            city: f.city.value.trim(),
            latitude: f.latitude.value || null,
            longitude: f.longitude.value || null,
            is_default: f.is_default.checked,
          });
          UI.toast("Address added", "success");
          renderAddresses(container);
        } catch (err) { UI.toastErr(err); }
      });

      container.querySelectorAll("[data-del-addr]").forEach((b) => b.onclick = async () => {
        if (!(await UI.confirmModal("Delete address?", "This cannot be undone.", "Delete", true))) return;
        try {
          await API.del(`/customer/addresses/${b.dataset.delAddr}/`);
          UI.toast("Deleted", "success");
          renderAddresses(container);
        } catch (err) { UI.toastErr(err); }
      });
    });
  }

  // ---------- Profile ----------
  async function renderProfile(container) {
    await UI.withLoading(container, async () => {
      const u = Session.user;
      const profile = await API.get("/customer/me/");
      container.innerHTML = `
        <div class="page-header"><div><h2>My Profile</h2><div class="desc">Account + preferences.</div></div></div>
        <div class="grid cols-2">
          <div class="card">
            <div class="card-title">Account</div>
            <div class="kv"><span class="k">Username</span><span class="v">${UI.esc(u.username)}</span></div>
            <div class="kv"><span class="k">Email</span><span class="v">${UI.esc(u.email)}</span></div>
            <div class="kv"><span class="k">Phone</span><span class="v">${UI.esc(u.phone_number)} ${u.phone_verified ? "(verified)" : "(unverified)"}</span></div>
            <div class="kv"><span class="k">Role</span><span class="v">${UI.esc(u.role)}</span></div>
            <div class="kv"><span class="k">Wallet balance</span><span class="v">${UI.money(profile.wallet_balance)}</span></div>
            <div class="kv"><span class="k">Joined</span><span class="v">${UI.fmtDate(u.date_joined)}</span></div>
          </div>
          <div class="card">
            <div class="card-title">Preferences</div>
            <form id="pref-form">
              <div class="field"><label>Date of birth</label><input class="input" type="date" name="date_of_birth" value="${profile.date_of_birth || ""}" /></div>
              <div class="field"><label>Preferred language</label>
                <select class="input" name="preferred_language">
                  <option value="en" ${profile.preferred_language === "en" ? "selected" : ""}>English</option>
                  <option value="ur" ${profile.preferred_language === "ur" ? "selected" : ""}>Urdu</option>
                  <option value="roman_ur" ${profile.preferred_language === "roman_ur" ? "selected" : ""}>Roman Urdu</option>
                </select>
              </div>
              <button class="btn" type="submit">Save</button>
            </form>
          </div>
        </div>`;
      document.getElementById("pref-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = e.target;
        try {
          await API.patch("/customer/me/", {
            date_of_birth: f.date_of_birth.value || null,
            preferred_language: f.preferred_language.value,
          });
          UI.toast("Preferences saved", "success");
        } catch (err) { UI.toastErr(err); }
      });
    });
  }

  return {
    renderShop, renderCart, renderCheckout, renderOrders, renderOrderDetail,
    renderPrescriptions, renderAddresses, renderProfile,
  };
})();
