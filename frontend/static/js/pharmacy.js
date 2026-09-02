const Pharmacy = (() => {
  let pollTimer = null;
  const stopPoll = () => { if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; } };

  async function renderDashboard(container) {
    await UI.withLoading(container, async () => {
      const [p, inv, orders] = await Promise.all([
        API.get("/pharmacy/me/"),
        API.unwrap(API.get("/pharmacy/inventory/")),
        API.unwrap(API.get("/pharmacy/orders/incoming/")),
      ]);
      const lowStock = inv.results.filter((i) => i.is_low_stock).length;

      container.innerHTML = `
        <div class="page-header"><div><h2>Pharmacy Dashboard</h2><div class="desc">${UI.esc(p.business_name)} · license ${UI.esc(p.license_number)}</div></div></div>
        ${p.is_verified ? "" : `<div class="banner warn"><b>Not verified yet.</b> You can receive orders, but an admin should flip "is_verified" in Django admin for production trust.</div>`}
        <div class="grid cols-3">
          <div class="card stat"><span class="value">${inv.results.length}</span><span class="label">Inventory items</span></div>
          <div class="card stat"><span class="value" style="color:${lowStock ? "#d97706" : "inherit"}">${lowStock}</span><span class="label">Low stock alerts</span></div>
          <div class="card stat"><span class="value">${orders.results.length}</span><span class="label">Active orders</span></div>
        </div>
        <div class="grid cols-2" style="margin-top:16px">
          <div class="card">
            <div class="card-title">Shop profile</div>
            <form id="ph-form">
              <div class="field"><label>Business name</label><input class="input" name="business_name" value="${UI.esc(p.business_name)}" required /></div>
              <div class="field"><label>Address line</label><input class="input" name="address_line" value="${UI.esc(p.address_line || "")}" /></div>
              <div class="form-row">
                <div class="field"><label>City</label><input class="input" name="city" value="${UI.esc(p.city || "")}" /></div>
                <div class="field"><label>Status</label>
                  <select class="input" name="is_open">
                    <option value="true" ${p.is_open ? "selected" : ""}>Open — visible to customers</option>
                    <option value="false" ${!p.is_open ? "selected" : ""}>Closed — hidden from directory</option>
                  </select>
                </div>
              </div>
              <div class="form-row">
                <div class="field"><label>Latitude</label><input class="input" name="latitude" value="${p.latitude ?? ""}" /></div>
                <div class="field"><label>Longitude</label><input class="input" name="longitude" value="${p.longitude ?? ""}" /></div>
              </div>
              <button class="btn" type="submit">Save Profile</button>
            </form>
          </div>
          <div class="card">
            <div class="card-title">Getting started</div>
            <ol style="padding-left:18px;color:#334155;font-size:13.5px;line-height:1.9">
              <li>Complete your shop profile here.</li>
              <li>Add stock under <b>Inventory</b> (needs medicines in the catalog — seed them from Test Utilities if missing).</li>
              <li>Customers order; watch <b>Incoming Orders</b> and move each through accept → preparing → ready for pickup.</li>
              <li>Verify customer prescriptions by Rx number under <b>Rx Verification</b>.</li>
            </ol>
          </div>
        </div>`;

    document.getElementById("ph-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = e.target;
        try {
          await API.patch("/pharmacy/me/", {
            business_name: f.business_name.value.trim(),
            address_line: f.address_line.value.trim(),
            city: f.city.value.trim(),
            is_open: f.is_open.value === "true",
            latitude: f.latitude.value === "" ? null : f.latitude.value,
            longitude: f.longitude.value === "" ? null : f.longitude.value,
          });
          UI.toast("Profile saved", "success");
        } catch (err) { UI.toastErr(err); }
      });
    });
  }

  // ---------- Inventory ----------
  async function renderInventory(container) {
    stopPoll();
    await UI.withLoading(container, async () => {
      const [invData, medsData] = await Promise.all([
        API.unwrap(API.get("/pharmacy/inventory/")),
        fetchAllMedicines(),
      ]);
      const meds = medsData;

      container.innerHTML = `
        <div class="page-header"><div><h2>Inventory</h2><div class="desc">Stock rows are per pharmacy. Low-stock rows are highlighted.</div></div></div>
        <div class="grid cols-2">
          <div class="card" style="grid-column:1/-1">
            <div class="card-title">Add stock row
              <span class="spacer"></span>
              <span class="hint">Duplicate medicine rows are rejected by the API — edit existing rows below.</span>
            </div>
            <form id="inv-form" class="inline-form">
              <div class="field" style="flex:2;min-width:220px"><label>Medicine</label>
                <select class="input" name="medicine_id" required>
                  <option value="">Select medicine...</option>
                  ${meds.map((m) => `<option value="${m.id}">${UI.esc(m.name)}${m.strength ? " " + UI.esc(m.strength) : ""} (#${m.id})</option>`).join("")}
                </select>
              </div>
              <div class="field"><label>Qty in stock</label><input class="input" type="number" name="quantity_in_stock" min="0" value="50" required /></div>
              <div class="field"><label>Selling price (Rs)</label><input class="input" type="number" step="0.01" min="0" name="selling_price" placeholder="e.g. 45" required /></div>
              <div class="field"><label>Reorder at</label><input class="input" type="number" name="reorder_threshold" min="0" value="10" /></div>
              <button class="btn" type="submit">Add Stock Row</button>
            </form>
          </div>
        </div>
        <div class="card">
          <div class="card-title">Current stock (${invData.results.length})</div>
          ${invData.results.length === 0 ? UI.emptyState("No stock rows", "Add your first item above.") : `
          <div class="table-wrap">
            <table class="table">
              <tr><th>Medicine</th><th>Qty</th><th>Price</th><th>Reorder at</th><th>Status</th><th>Updated</th><th></th></tr>
              ${invData.results.map((i) => `
                <tr class="${i.is_low_stock ? "low" : ""}">
                  <td><b>${UI.esc(i.medicine.name)}</b><br /><span class="hint">#${i.medicine.id}${i.medicine.requires_prescription ? " · Rx" : ""}</span></td>
                  <td><input type="number" class="input qty-input" style="width:70px" data-q="${i.id}" value="${i.quantity_in_stock}" /></td>
                  <td><input type="number" class="input qty-input" style="width:90px" step="0.01" data-p="${i.id}" value="${Number(i.selling_price)}" /></td>
                  <td>${i.reorder_threshold}</td>
                  <td>${i.is_low_stock ? '<span class="badge amber">LOW STOCK</span>' : '<span class="badge green">OK</span>'}</td>
                  <td class="hint">${UI.fmtDate(i.updated_at)}</td>
                  <td>
                    <button class="btn sm secondary" data-save="${i.id}">Save</button>
                    <button class="link-btn" data-del="${i.id}">Delete</button>
                  </td>
                </tr>`).join("")}
            </table>
          </div>`}
        </div>`;

      document.getElementById("inv-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = e.target;
        if (!f.medicine_id.value) { UI.toast("Pick a medicine", "error"); return; }
        try {
          await API.post("/pharmacy/inventory/", {
            medicine_id: Number(f.medicine_id.value),
            quantity_in_stock: Number(f.quantity_in_stock.value),
            selling_price: f.selling_price.value,
            reorder_threshold: Number(f.reorder_threshold.value || 10),
          });
          UI.toast("Stock row added", "success");
          renderInventory(container);
        } catch (err) { UI.toastErr(err); }
      });

      container.querySelectorAll("[data-save]").forEach((b) => b.onclick = async () => {
        try {
          await API.patch(`/pharmacy/inventory/${b.dataset.save}/`, {
            quantity_in_stock: Number(container.querySelector(`[data-q="${b.dataset.save}"]`).value),
            selling_price: container.querySelector(`[data-p="${b.dataset.save}"]`).value,
          });
          UI.toast("Row updated", "success");
        } catch (err) { UI.toastErr(err); }
      });

      container.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => {
        if (!(await UI.confirmModal("Delete stock row?", "Customers can no longer be priced against it.", "Delete", true))) return;
        try {
          await API.del(`/pharmacy/inventory/${b.dataset.del}/`);
          UI.toast("Deleted", "success");
          renderInventory(container);
        } catch (err) { UI.toastErr(err); }
      });
    });
  }

  async function fetchAllMedicines() {
    const out = [];
    let page = 1;
    while (page <= 10) {
      const d = API.unwrap(await API.get(`/catalog/medicines/?page=${page}&is_active=true`));
      out.push(...d.results);
      if (!d.count || out.length >= d.count) break;
      page += 1;
    }
    return out;
  }

  // ---------- Incoming orders ----------
  async function renderOrders(container) {
    await UI.withLoading(container, async () => {
      const { results } = API.unwrap(await API.get("/pharmacy/orders/incoming/"));
      const actionsFor = (status) => {
        switch (status) {
          case "pending":
          case "under_review":
            return [["accept", "Accept", ""], ["reject", "Reject", "outline-danger"]];
          case "accepted":
            return [["preparing", "Start Preparing", ""], ["reject", "Reject", "outline-danger"]];
          case "preparing":
            return [["ready-for-pickup", "Ready for Pickup", ""]];
          default:
            return [];
        }
      };

      container.innerHTML = `
        <div class="page-header"><div><h2>Incoming Orders</h2><div class="desc">Active orders only (delivered/cancelled hidden). Refreshes every 8s.</div></div></div>
        ${results.length === 0 ? UI.emptyState("No active orders", "New orders will appear here automatically.") :
          results.map((o) => `
          <div class="order-card">
            <div class="oc-head">
              <span class="oc-id">Order #${o.id}</span>
              ${UI.statusBadge(o.status)}
              ${o.is_paid ? '<span class="badge green">Paid</span>' : ""}
              <span class="oc-date">${UI.fmtDate(o.created_at)}</span>
              <b>${UI.money(o.total)}</b>
            </div>
            <div class="oc-body">
              <div>
                ${(o.items || []).map((i) => `<div>${UI.esc(i.medicine.name)} × ${i.quantity} @ ${UI.money(i.unit_price)}</div>`).join("")}
              </div>
              <div style="min-width:220px">
                ${o.delivery_address ? `<div class="hint">Deliver to:</div><div>${UI.esc(o.delivery_address.address_line)}, ${UI.esc(o.delivery_address.city)}</div>` : '<div class="hint">No address on order</div>'}
                <div class="hint" style="margin-top:4px">${UI.esc(o.payment_method)} · Customer #${typeof o.customer === "object" && o.customer ? o.customer.user?.id ?? o.customer.id : o.customer}</div>
              </div>
            </div>
            <div class="btn-group" style="margin-top:12px">
              ${actionsFor(o.status).map(([act, label, cls]) => `<button class="btn sm ${cls}" data-act="${act}" data-order="${o.id}">${label}</button>`).join("")}
              ${o.status === "ready_for_pickup" ? '<span class="badge teal">Waiting for rider dispatch/pickup…</span>' : ""}
            </div>
          </div>`).join("")}`;

      container.querySelectorAll("[data-act]").forEach((b) => b.onclick = async () => {
        b.disabled = true;
        try {
          const updated = await API.post(`/pharmacy/orders/${b.dataset.order}/${b.dataset.act}/`);
          UI.toast(`Order #${updated.id} → ${UI.STATUS_LABEL(updated.status)}`, "success");
          renderOrders(container);
        } catch (err) {
          b.disabled = false;
          UI.toastErr(err);
        }
      });

      clearTimeout(pollTimer);
      pollTimer = setTimeout(() => {
        if (location.hash === "#/ph-orders") renderOrders(container);
      }, 8000);
    });
  }

  // ---------- Prescription verification ----------
  async function renderRxVerify(container) {
    await UI.withLoading(container, async () => {
      const { results } = API.unwrap(await API.get("/pharmacy/prescriptions/incoming/"));
      const RX_COLORS = { uploaded: "gray", processing: "amber", needs_review: "amber", verified: "green", rejected: "red" };
      const statusBadge = (s) => `<span class="badge ${RX_COLORS[s] || "gray"}">${UI.esc(s.replace(/_/g, " "))}</span>`;

      container.innerHTML = `
        <div class="page-header"><div><h2>Rx Verification</h2><div class="desc">Prescriptions assigned to your pharmacy, newest first. Approve or reject each.</div></div></div>
        ${results.length === 0 ? UI.emptyState("No prescriptions yet", "When a customer uploads a prescription to your pharmacy it will appear here for review.") :
          results.map((p) => `
          <div class="order-card">
            <div class="oc-head">
              <span class="oc-id">Rx #${p.id}</span>
              ${statusBadge(p.status)}
              <span class="oc-date">${UI.fmtDate(p.created_at)}</span>
              <span class="hint">Customer: ${UI.esc(p.customer_name || `#${p.customer}`)}</span>
            </div>
            <div class="oc-body">
              <div>
                ${(p.items || []).length === 0
                  ? '<span class="hint">No extracted items yet</span>'
                  : `<table class="table"><tr><th>Raw text</th><th>Matched</th><th>Dosage</th><th>Qty</th><th>Confidence</th></tr>
                     ${p.items.map((it) => `
                       <tr>
                         <td>${UI.esc(it.raw_medicine_text)}</td>
                         <td>${it.medicine ? UI.esc(it.medicine.name) : '<span class="badge red">unmatched</span>'}</td>
                         <td>${UI.esc(`${it.dosage || ""}${it.frequency ? " · " + it.frequency : ""}`)}</td>
                         <td>${it.quantity ?? "—"}</td>
                         <td>${it.confidence != null ? Math.round(it.confidence * 100) + "%" : "—"}</td>
                       </tr>`).join("")}
                   </table>`}
                ${(p.risk_flags || []).length === 0
                  ? ""
                  : `<div class="rx-risks">${p.risk_flags.map((r) => `
                      <div class="ai-risk ${r.severity}">
                        <b>${r.severity === "high" ? "⚠️" : "⚡"} ${UI.esc(r.title)}</b>
                        <div>${UI.esc(r.message)}</div>
                        ${r.items && r.items.length ? '<div class="risk-items">' + r.items.map((t) => `<span>${UI.esc(t)}</span>`).join("") + "</div>" : ""}
                      </div>`).join("")}</div>`}
              </div>
              <div style="min-width:220px">
                <div class="hint">Dr. ${UI.esc(p.doctor_name || "—")} · Patient ${UI.esc(p.patient_name || "—")}</div>
                ${p.file ? `<div style="margin-top:6px"><a href="${UI.mediaUrl(p.file)}" target="_blank" class="mono">View uploaded file</a></div>` : ""}
              </div>
            </div>
            ${["uploaded", "processing", "needs_review"].includes(p.status) ? `
            <div class="btn-group" style="margin-top:12px">
              <button class="btn sm" data-rx="${p.id}" data-decision="approved">Approve</button>
              <button class="btn sm outline-danger" data-rx="${p.id}" data-decision="rejected">Reject</button>
              <button class="btn sm secondary" data-rx="${p.id}" data-decision="needs_info">Needs info</button>
            </div>` : ''}
          </div>`).join("")}`;

      container.querySelectorAll("[data-rx]").forEach((b) => b.onclick = async () => {
        const id = b.dataset.rx, decision = b.dataset.decision;
        let notes = "";
        if (decision !== "approved") {
          notes = await promptText("Add a short note for this decision (optional):") || "";
        }
        b.disabled = true;
        try {
          const res = await API.post(`/pharmacy/prescriptions/${id}/verify/`, { decision, notes });
          UI.toast(`Rx #${res.prescription_id} → ${UI.esc(res.status)}`, "success");
          renderRxVerify(container);
        } catch (err) { b.disabled = false; UI.toastErr(err); }
      });
    });
  }

  function promptText(label) {
    return new Promise((resolve) => {
      UI.modal(
        `<h3>Notes</h3><p style="color:var(--muted);font-size:14px">${UI.esc(label)}</p>
         <textarea class="input" id="rx-note" rows="2"></textarea>
         <div class="modal-actions">
           <button class="btn secondary" data-x="no">Cancel</button>
           <button class="btn" data-x="yes">Save note</button>
         </div>`,
        (backdrop, close) => {
          backdrop.querySelector('[data-x="no"]').onclick = () => { close(); resolve(""); };
          backdrop.querySelector('[data-x="yes"]').onclick = () => {
            const v = (backdrop.querySelector("#rx-note").value || "").trim();
            close(); resolve(v);
          };
        }
      );
    });
  }

  // ---------- Forecasts ----------
  async function renderForecasts(container) {
    await UI.withLoading(container, async () => {
      const { results } = API.unwrap(await API.get("/pharmacy/forecasts/"));
      container.innerHTML = `
        <div class="page-header"><div><h2>Demand Forecasts</h2><div class="desc">AI prediction from your real order history (last 30 days, next 7 days).</div></div>
          <div><button class="btn" id="refresh-forecasts">↻ Refresh forecasts</button></div></div>
        <div class="card">
          ${results.length === 0 ? UI.emptyState("No forecasts", "Click 'Refresh forecasts' to generate predictions from your order history.") : `
          <div class="table-wrap">
            <table class="table">
              <tr><th>Medicine</th><th>Current stock</th><th>Expected demand</th><th>Recommended restock</th><th>Generated</th></tr>
              ${results.map((f) => `
                <tr>
                  <td>${UI.esc(f.medicine.name)}</td><td>${f.current_stock}</td><td>${f.expected_demand}</td>
                  <td><b>${f.recommended_restock}</b></td><td class="hint">${UI.fmtDate(f.generated_at)}</td>
                </tr>`).join("")}
            </table>
          </div>`}
        </div>`;
      document.getElementById("refresh-forecasts")?.addEventListener("click", async (e) => {
        e.target.disabled = true;
        try {
          const res = await API.post("/pharmacy/forecasts/generate/", { lookback_days: 30, horizon_days: 7 });
          UI.toast(`Forecasts updated for ${res.count} medicines`, "success");
          renderForecasts(container);
        } catch (err) { e.target.disabled = false; UI.toastErr(err); }
      });
    });
  }

  return { renderDashboard, renderInventory, renderOrders, renderRxVerify, renderForecasts, stopPoll };
})();
