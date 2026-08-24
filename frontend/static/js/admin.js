const Admin = (() => {
  let medsCache = [];
  let catsCache = [];
  let brandsCache = [];

  async function loadRefs() {
    const [m, c, b] = await Promise.all([
      fetchAllPages("/catalog/medicines/"),
      fetchAllPages("/catalog/categories/"),
      fetchAllPages("/catalog/brands/"),
    ]);
    medsCache = m; catsCache = c; brandsCache = b;
  }

  async function fetchAllPages(path) {
    const out = [];
    for (let page = 1; page <= 10; page++) {
      const d = API.unwrap(await API.get(`${path}${path.includes("?") ? "&" : "?"}page=${page}`));
      out.push(...d.results);
      if (!d.results.length) break;
    }
    return out;
  }

  // ---------- Catalog manager ----------
  async function renderCatalog(container) {
    await UI.withLoading(container, async () => {
      await loadRefs();
      container.innerHTML = `
        <div class="page-header"><div><h2>Catalog Manager</h2><div class="desc">Direct CRUD against /catalog/. Medicines must exist here before pharmacies can stock them.</div></div></div>
        <div class="grid cols-2">
          <div class="card">
            <div class="card-title">Categories (${catsCache.length})
              <span class="spacer"></span><button class="btn sm secondary" id="add-cat">+ Add</button>
            </div>
            ${catsCache.length === 0 ? UI.emptyState("None", "Add categories first.") : `
              <table class="table">
                ${catsCache.map((c) => `<tr><td>${UI.esc(c.name)}</td><td class="hint">${UI.esc(c.description || "")}</td>
                  <td style="text-align:right"><button class="link-btn" data-del-cat="${c.id}">Delete</button></td></tr>`).join("")}
              </table>`}
          </div>
          <div class="card">
            <div class="card-title">Brands (${brandsCache.length})
              <span class="spacer"></span><button class="btn sm secondary" id="add-brand">+ Add</button>
            </div>
            ${brandsCache.length === 0 ? UI.emptyState("None", "Add brands.") : `
              <table class="table">
                ${brandsCache.map((b) => `<tr><td>${UI.esc(b.name)}</td>
                  <td style="text-align:right"><button class="link-btn" data-del-brand="${b.id}">Delete</button></td></tr>`).join("")}
              </table>`}
          </div>
        </div>
        <div class="card" style="margin-top:16px">
          <div class="card-title">Medicines (${medsCache.length})<span class="spacer"></span><button class="btn sm" id="add-med">+ Add Medicine</button></div>
          ${medsCache.length === 0 ? UI.emptyState("Catalog is empty", "Add a medicine or run the Demo Seeder below.") : `
          <div class="table-wrap">
            <table class="table">
              <tr><th>ID</th><th>Name</th><th>Generic</th><th>Form / Strength</th><th>Category</th><th>Brand</th><th>Rx</th><th></th></tr>
              ${medsCache.map((m) => `
                <tr>
                  <td class="mono">${m.id}</td>
                  <td><b>${UI.esc(m.name)}</b></td>
                  <td>${UI.esc(m.generic_name || "—")}</td>
                  <td>${UI.esc([m.form, m.strength].filter(Boolean).join(" · ") || "—")}</td>
                  <td>${m.category ? UI.esc(m.category.name) : "—"}</td>
                  <td>${m.brand ? UI.esc(m.brand.name) : "—"}</td>
                  <td>${m.requires_prescription ? '<span class="rx-badge">Rx</span>' : '<span class="badge teal">OTC</span>'}</td>
                  <td><button class="link-btn" data-edit-med="${m.id}">Edit</button> <button class="link-btn" data-del-med="${m.id}">Delete</button></td>
                </tr>`).join("")}
            </table>
          </div>`}
        </div>
        <div class="card" style="margin-top:16px">
          <div class="card-title">Demo Data Seeder</div>
          <p class="hint" style="margin-bottom:10px">One click creates typical Pakistani OTC/Rx medicines (skips ones already present by name). Perfect before a demo run.</p>
          <div class="btn-group">
            <button class="btn" id="seed-basic">Seed basic catalog (categories + brands + 12 medicines)</button>
          </div>
          <p class="hint" style="margin-top:8px">Full data management (including deletion of users/orders) lives in the Django admin at /admin/.</p>
          <div id="seed-out" style="margin-top:12px"></div>
        </div>`;

      document.getElementById("add-cat").onclick = () => promptModal("New category", [{ name: "name", label: "Name", req: true }, { name: "description", label: "Description" }], (data) =>
        API.post("/catalog/categories/", data).then(() => renderCatalog(container)));

      document.getElementById("add-brand").onclick = () => promptModal("New brand", [{ name: "name", label: "Name", req: true }], (data) =>
        API.post("/catalog/brands/", data).then(() => renderCatalog(container)));

      container.querySelectorAll("[data-del-cat]").forEach((b) => b.onclick = () =>
        confirmThen(`Delete category #${b.dataset.delCat}?`, () => API.del(`/catalog/categories/${b.dataset.delCat}/`).then(() => renderCatalog(container))));
      container.querySelectorAll("[data-del-brand]").forEach((b) => b.onclick = () =>
        confirmThen(`Delete brand #${b.dataset.delBrand}?`, () => API.del(`/catalog/brands/${b.dataset.delBrand}/`).then(() => renderCatalog(container))));

      container.querySelectorAll("[data-del-med]").forEach((b) => b.onclick = () =>
        confirmThen(`Delete medicine #${b.dataset.delMed}?`, () => API.del(`/catalog/medicines/${b.dataset.delMed}/`).then(() => renderCatalog(container))));

      container.querySelectorAll("[data-edit-med]").forEach((b) => b.onclick = () => medicineForm(medsCache.find((m) => m.id === Number(b.dataset.editMed)), container));

      document.getElementById("add-med").onclick = () => medicineForm(null, container);
      document.getElementById("seed-basic").onclick = () => seedBasic(container);
    });
  }

  function confirmThen(text, fn) {
    UI.confirmModal("Are you sure?", text, "Delete", true).then(async (ok) => {
      if (!ok) return;
      try { await fn(); UI.toast("Done", "success"); } catch (err) { UI.toastErr(err); }
    });
  }

  function promptModal(title, fields, onSubmit) {
    UI.modal(`<h3>${UI.esc(title)}</h3>
      <form id="pm-form">
        ${fields.map((f) => `<div class="field"><label>${f.label}</label><input class="input" name="${f.name}" ${f.req ? "required" : ""} /></div>`).join("")}
        <div class="modal-actions"><button type="button" class="btn secondary" data-x="cancel">Cancel</button>
        <button type="submit" class="btn">Save</button></div>
      </form>`, (backdrop, close) => {
      backdrop.querySelector('[data-x="cancel"]').onclick = close;
      backdrop.querySelector("#pm-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const data = {};
        fields.forEach((f) => (data[f.name] = e.target[f.name].value.trim()));
        try { await onSubmit(data); close(); } catch (err) { UI.toastErr(err); }
      });
    });
  }

  function medicineForm(existing, container) {
    const m = existing || {};
    UI.modal(`<h3>${existing ? "Edit" : "New"} medicine</h3>
      <form id="med-form">
        <div class="field"><label>Name *</label><input class="input" name="name" value="${UI.esc(m.name || "")}" required /></div>
        <div class="form-row">
          <div class="field"><label>Generic name</label><input class="input" name="generic_name" value="${UI.esc(m.generic_name || "")}" /></div>
          <div class="field"><label>Strength</label><input class="input" name="strength" placeholder="500mg" value="${UI.esc(m.strength || "")}" /></div>
        </div>
        <div class="form-row">
          <div class="field"><label>Form</label>
            <select class="input" name="form">
              ${["", "tablet", "capsule", "syrup", "suspension", "injection", "inhaler", "cream", "drops"].map((v) => `<option value="${v}" ${(m.form || "") === v ? "selected" : ""}>${v || "—"}</option>`).join("")}
            </select>
          </div>
          <div class="field"><label>Requires prescription?</label>
            <select class="input" name="requires_prescription">
              <option value="true" ${m.requires_prescription !== false ? "selected" : ""}>Yes — Rx only</option>
              <option value="false" ${m.requires_prescription === false ? "selected" : ""}>No — OTC</option>
            </select>
          </div>
        </div>
        <div class="form-row">
          <div class="field"><label>Category</label>
            <select class="input" name="category"><option value="">—</option>
              ${catsCache.map((c) => `<option value="${c.id}" ${m.category && m.category.id === c.id ? "selected" : ""}>${UI.esc(c.name)}</option>`).join("")}
            </select>
          </div>
          <div class="field"><label>Brand</label>
            <select class="input" name="brand"><option value="">—</option>
              ${brandsCache.map((b) => `<option value="${b.id}" ${m.brand && m.brand.id === b.id ? "selected" : ""}>${UI.esc(b.name)}</option>`).join("")}
            </select>
          </div>
        </div>
        <div class="field"><label>Description</label><textarea class="input" name="description">${UI.esc(m.description || "")}</textarea></div>
        <label class="checkbox-row"><input type="checkbox" name="is_active" ${m.is_active !== false ? "checked" : ""} /> Active</label>
        <div class="modal-actions">
          <button type="button" class="btn secondary" data-x="cancel">Cancel</button>
          <button type="submit" class="btn">${existing ? "Save changes" : "Create"}</button>
        </div>
      </form>`, (backdrop, close) => {
      backdrop.querySelector('[data-x="cancel"]').onclick = close;
      backdrop.querySelector("#med-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = e.target;
        const payload = {
          name: f.name.value.trim(),
          generic_name: f.generic_name.value.trim(),
          strength: f.strength.value.trim(),
          form: f.form.value,
          requires_prescription: f.requires_prescription.value === "true",
          category: f.category.value ? Number(f.category.value) : null,
          brand: f.brand.value ? Number(f.brand.value) : null,
          description: f.description.value.trim(),
          is_active: f.is_active.checked,
        };
        try {
          if (existing) await API.patch(`/catalog/medicines/${existing.id}/`, payload);
          else await API.post("/catalog/medicines/", payload);
          UI.toast(existing ? "Medicine updated" : "Medicine created", "success");
          close();
          renderCatalog(container);
        } catch (err) { UI.toastErr(err); }
      });
    });
  }

  // ---------- Demo seeder ----------
  const SEED_CATEGORIES = [
    ["Pain Relief", "Analgesics and antipyretics"],
    ["Antibiotics", "Bacterial infection treatment"],
    ["Cold & Flu", "Cough, cold and flu remedies"],
    ["Vitamins & Supplements", "Daily nutrition support"],
    ["Stomach Care", "Acidity, digestion and gut health"],
  ];
  const SEED_BRANDS = ["GSK", "Abbott", "Searle", "Getz Pharma", "Hilton Pharma"];
  const SEED_MEDICINES = [
    ["Panadol", "paracetamol", "500mg", "tablet", "Pain Relief", "GSK", false, "Relieves pain and fever."],
    ["Panadol Extra", "paracetamol + caffeine", "500mg", "tablet", "Pain Relief", "GSK", false, "Stronger relief for headaches."],
    ["Brufen", "ibuprofen", "400mg", "tablet", "Pain Relief", "Abbott", false, "NSAID for pain and inflammation."],
    ["Disprin", "aspirin", "300mg", "tablet", "Pain Relief", "GSK", false, "Pain, fever and blood thinning."],
    ["Augmentin", "amoxicillin + clavulanic acid", "625mg", "tablet", "Antibiotics", "GSK", true, "Broad spectrum antibiotic."],
    ["Flagyl", "metronidazole", "400mg", "tablet", "Antibiotics", "Searle", true, "Anaerobic bacterial infections."],
    ["Ciproxin", "ciprofloxacin", "500mg", "tablet", "Antibiotics", "Getz Pharma", true, "Fluoroquinolone antibiotic."],
    ["Calpol", "paracetamol", "120mg/5ml", "syrup", "Cold & Flu", "GSK", false, "Fever relief for children."],
    ["Rigix", "cetirizine", "10mg", "tablet", "Cold & Flu", "Getz Pharma", false, "Allergy relief antihistamine."],
    ["Ventolin Inhaler", "salbutamol", "100mcg", "inhaler", "Cold & Flu", "GSK", true, "Asthma reliever inhaler."],
    ["Surbex-Z", "vitamin B-complex + zinc", "", "tablet", "Vitamins & Supplements", "Abbott", false, "Immunity and energy support."],
    ["Risek", "omeprazole", "20mg", "capsule", "Stomach Care", "Getz Pharma", true, "Acidity and reflux control."],
    ["Motilium", "domperidone", "10mg", "tablet", "Stomach Care", "Abbott", false, "Nausea and vomiting relief."],
  ];

  async function seedBasic(container) {
    const out = document.getElementById("seed-out");
    out.innerHTML = '<div class="spinner"></div>';
    const log = [];
    try {
      for (const [name, desc] of SEED_CATEGORIES) {
        const exists = catsCache.find((c) => c.name === name);
        log.push(exists ? `category ok: ${name}` : `category created: ${name}`);
        if (!exists) await API.post("/catalog/categories/", { name, description: desc });
      }
      await loadRefs();
      for (const name of SEED_BRANDS) {
        const exists = brandsCache.find((b) => b.name === name);
        log.push(exists ? `brand ok: ${name}` : `brand created: ${name}`);
        if (!exists) await API.post("/catalog/brands/", { name });
      }
      await loadRefs();
      for (const [medName, generic, strength, form, cat, brandN, rx, desc] of SEED_MEDICINES) {
        const search = API.unwrap(await API.get(`/catalog/medicines/?q=${encodeURIComponent(medName)}`));
        if (search.results.some((m) => m.name.toLowerCase() === medName.toLowerCase())) {
          log.push(`medicine ok: ${medName}`);
          continue;
        }
        const category = catsCache.find((c) => c.name === cat);
        const brandObj = brandsCache.find((b) => b.name === brandN);
        await API.post("/catalog/medicines/", {
          name: medName, generic_name: generic, strength, form,
          category: category ? category.id : null,
          brand: brandObj ? brandObj.id : null,
          requires_prescription: rx,
          description: desc,
          is_active: true,
        });
        log.push(`medicine created: ${medName}`);
      }
      out.innerHTML = `<pre class="code">${log.join("\n")}\nDONE — catalog seeded.</pre>`;
      UI.toast("Demo catalog ready!", "success");
      renderCatalog(container);
    } catch (err) {
      out.innerHTML = `<div class="banner error">${UI.errText(err)}</div>`;
    }
  }

  return { renderCatalog };
})();
