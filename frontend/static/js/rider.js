const Rider = (() => {
  let offerTimer = null;
  const stopPoll = () => { if (offerTimer) { clearTimeout(offerTimer); offerTimer = null; } };

  async function renderDashboard(container) {
    await UI.withLoading(container, async () => {
      const [r, offers, deliveries] = await Promise.all([
        API.get("/rider/me/"),
        API.unwrap(API.get("/rider/offers/")),
        API.unwrap(API.get("/rider/deliveries/")),
      ]);

      container.innerHTML = `
        <div class="page-header"><div><h2>Rider Dashboard</h2><div class="desc">${UI.esc(Session.user.username)} · ${UI.esc(r.vehicle_type || "no vehicle set")}</div></div></div>
        ${r.is_verified ? "" : `<div class="banner warn"><b>Account not verified.</b> Dispatch may not include you until an admin sets "is_verified" in Django admin.</div>`}
        <div class="grid cols-3">
          <div class="card stat"><span class="value">${offers.results.length}</span><span class="label">Pending offers</span></div>
          <div class="card stat"><span class="value">${deliveries.results.length}</span><span class="label">Active deliveries</span></div>
          <div class="card stat"><span class="value">${Number(r.rating).toFixed(1)}</span><span class="label">Rating</span></div>
        </div>
        <div class="grid cols-2" style="margin-top:16px">
          <div class="card">
            <div class="card-title">Profile &amp; availability</div>
            <form id="rider-form">
              <div class="form-row">
                <div class="field"><label>Vehicle type</label>
                  <select class="input" name="vehicle_type">
                    ${["bike", "motorcycle", "car", "bicycle"].map((v) => `<option value="${v}" ${r.vehicle_type === v ? "selected" : ""}>${v}</option>`).join("")}
                  </select>
                </div>
                <div class="field"><label>Availability</label>
                  <select class="input" name="is_available">
                    <option value="true" ${r.is_available ? "selected" : ""}>Online — accepting offers</option>
                    <option value="false" ${!r.is_available ? "selected" : ""}>Offline</option>
                  </select>
                </div>
              </div>
              <div class="field"><label>CNIC number</label><input class="input" name="cnic_number" value="${UI.esc(r.cnic_number || "")}" placeholder="35202-XXXXXXX-X" /></div>
              <button class="btn" type="submit">Save</button>
            </form>
            <p class="hint" style="margin-top:8px">Wallet: Rs ${Number(r.wallet_balance).toFixed(0)} · verified: ${r.is_verified ? "yes" : "no"} (read-only)</p>
          </div>
          <div class="card">
            <div class="card-title">Live location ping</div>
            <p class="hint" style="margin-bottom:10px">POST /rider/location/ — feeds customer tracking + dispatch ETA.</p>
            <div class="btn-group" style="margin-bottom:12px">
              <button class="btn secondary" id="geo-btn">Use my GPS location</button>
            </div>
            <form id="loc-form" class="inline-form">
              <div class="field"><label>Latitude</label><input class="input" name="latitude" id="lat-in" value="${r.current_latitude ?? "31.520370"}" required /></div>
              <div class="field"><label>Longitude</label><input class="input" name="longitude" id="lng-in" value="${r.current_longitude ?? "74.358750"}" required /></div>
              <button class="btn" type="submit">Send Ping</button>
            </form>
          </div>
        </div>`;

      document.getElementById("rider-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = e.target;
        try {
          await API.patch("/rider/me/", {
            vehicle_type: f.vehicle_type.value,
            is_available: f.is_available.value === "true",
            cnic_number: f.cnic_number.value.trim() || null,
          });
          UI.toast("Rider profile saved", "success");
        } catch (err) { UI.toastErr(err); }
      });

      document.getElementById("geo-btn").onclick = () => {
        if (!navigator.geolocation) { UI.toast("Geolocation not supported", "error"); return; }
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            document.getElementById("lat-in").value = pos.coords.latitude.toFixed(6);
            document.getElementById("lng-in").value = pos.coords.longitude.toFixed(6);
            UI.toast("GPS coordinates captured", "success");
          },
          () => UI.toast("Could not get location permission", "error")
        );
      };

      document.getElementById("loc-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = e.target;
        try {
          await API.post("/rider/location/", { latitude: f.latitude.value, longitude: f.longitude.value });
          UI.toast("Location ping sent", "success");
        } catch (err) { UI.toastErr(err); }
      });
    });
  }

  // ---------- Offers ----------
  async function renderOffers(container) {
    await UI.withLoading(container, async () => {
      let offers = [];
      try {
        offers = API.unwrap(await API.get("/rider/offers/")).results;
      } catch (err) {
        container.innerHTML = `<div class="banner error">${UI.errText(err)}</div>`;
        return;
      }
      container.innerHTML = `
        <div class="page-header"><div><h2>Delivery Offers</h2><div class="desc">Dispatch requests for you. Polling every 5s.</div></div></div>
        ${offers.length === 0 ? UI.emptyState("No pending offers", "When a pharmacy marks an order ready for pickup, dispatch sends you an offer here.") :
          offers.map((o) => `
            <div class="order-card">
              <div class="oc-head">
                <span class="oc-id">Offer #${o.id}</span>
                ${o.distance_km != null ? `<span class="badge blue">${Number(o.distance_km).toFixed(1)} km</span>` : ""}
                ${o.score != null ? `<span class="badge teal">score ${Number(o.score).toFixed(2)}</span>` : ""}
                <span class="badge amber">offered</span>
                <span class="oc-date">${UI.fmtDate(o.created_at)}</span>
              </div>
              <div class="oc-body">
                <span>Delivery assignment #${o.delivery} — accept to see full order details under My Deliveries.</span>
              </div>
              <div class="btn-group" style="margin-top:12px">
                <button class="btn sm" data-decide="accepted" data-offer="${o.id}">Accept Delivery</button>
                <button class="btn sm outline-danger" data-decide="declined" data-offer="${o.id}">Decline</button>
              </div>
            </div>`).join("")}`;

      container.querySelectorAll("[data-decide]").forEach((b) => b.onclick = async () => {
        b.disabled = true;
        try {
          await API.post(`/rider/offers/${b.dataset.offer}/respond/`, { decision: b.dataset.decide });
          UI.toast(b.dataset.decide === "accepted" ? "Offer accepted — check My Deliveries" : "Offer declined", "success");
          renderOffers(container);
        } catch (err) { b.disabled = false; UI.toastErr(err); }
      });

      clearTimeout(offerTimer);
      offerTimer = setTimeout(() => {
        if (location.hash === "#/r-offers") renderOffers(container);
      }, 5000);
    });
  }

  // ---------- Deliveries ----------
  async function renderDeliveries(container) {
    stopPoll();
    await UI.withLoading(container, async () => {
      const { results } = API.unwrap(await API.get("/rider/deliveries/"));
      let ordersById = {};
      try {
        const orders = API.unwrap(await API.get("/orders/")).results;
        orders.forEach((o) => (ordersById[o.id] = o));
      } catch {}

      container.innerHTML = `
        <div class="page-header"><div><h2>My Deliveries</h2><div class="desc">Active assignments. Move each through pickup → on the way → delivered.</div></div></div>
        ${results.length === 0 ? UI.emptyState("No active deliveries", "Accept an offer to get your first delivery assignment.") :
          results.map((d) => {
            const order = ordersById[d.order] || {};
            const status = order.status;
            return `
            <div class="order-card">
              <div class="oc-head">
                <span class="oc-id">Order #${d.order}</span>
                ${UI.statusBadge(status)}
                ${d.picked_up_at ? "" : '<span class="badge gray">not picked up</span>'}
                <span class="oc-date">assigned ${UI.fmtDate(d.assigned_at)}</span>
              </div>
              <div class="oc-body">
                <div style="flex:1">
                  ${(order.items || []).map((i) => `<div>${UI.esc(i.medicine.name)} × ${i.quantity}</div>`).join("") || '<span class="hint">item details unavailable</span>'}
                </div>
                <div style="min-width:230px">
                  ${order.delivery_address ? `<div class="hint">Deliver to:</div><div>${UI.esc(order.delivery_address.address_line)}, ${UI.esc(order.delivery_address.city)}</div>` : '<div class="hint">address unavailable</div>'}
                  <div class="hint" style="margin-top:4px">${order.payment_method === "cod" && !order.is_paid ? "<b>CASH ON DELIVERY — collect payment!</b>" : UI.esc(order.payment_method || "")}</div>
                </div>
              </div>
              <div class="btn-group" style="margin-top:12px">
                ${!d.picked_up_at
                  ? `<button class="btn sm" data-act="confirm-pickup" data-order="${d.order}">Confirm Pickup</button>`
                  : `${!d.delivered_at ? `<button class="btn sm secondary" data-act="start" data-order="${d.order}">Start Delivery</button>
                     <button class="btn sm" data-act="confirm-delivered" data-order="${d.order}">Confirm Delivered</button>` : ""}`}
                ${status === "ready_for_pickup" && !d.picked_up_at ? '<span class="hint" style="align-self:center">Head to the pharmacy, then confirm pickup.</span>' : ""}
              </div>
            </div>`;
          }).join("")}`;

      container.querySelectorAll("[data-act]").forEach((b) => b.onclick = async () => {
        b.disabled = true;
        try {
          await API.post(`/rider/deliveries/${b.dataset.order}/${b.dataset.act}/`);
          UI.toast(`Order #${b.dataset.order}: ${b.dataset.act.replace("-", " ")} done`, "success");
          renderDeliveries(container);
        } catch (err) {
          b.disabled = false;
          UI.toastErr(err);
        }
      });
    });
  }

  return { renderDashboard, renderOffers, renderDeliveries, stopPoll };
})();
