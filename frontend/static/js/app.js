const App = (() => {
  const routes = {
    customer: [
      ["Shop", "#/shop", "shop", () => Customer.renderShop(view())],
      ["Cart", "#/cart", "cart", () => Customer.renderCart(view()), true],
      ["Orders", "#/orders", "orders", () => Customer.renderOrders(view())],
      ["Prescriptions", "#/prescriptions", "rx", () => Customer.renderPrescriptions(view())],
      ["Addresses", "#/addresses", "addr", () => Customer.renderAddresses(view())],
      ["Profile", "#/profile", "profile", () => Customer.renderProfile(view())],
      ["Utilities", "#/utilities", "tools", () => Admin.renderCatalog(view()), false, true],
    ],
    pharmacy: [
      ["Dashboard", "#/ph-dashboard", "dash", () => Pharmacy.renderDashboard(view())],
      ["Inventory", "#/ph-inventory", "inv", () => Pharmacy.renderInventory(view())],
      ["Incoming Orders", "#/ph-orders", "orders", () => Pharmacy.renderOrders(view())],
      ["Rx Verification", "#/ph-prescriptions", "rx", () => Pharmacy.renderRxVerify(view())],
      ["Forecasts", "#/ph-forecasts", "chart", () => Pharmacy.renderForecasts(view())],
      ["Utilities", "#/utilities", "tools", () => Admin.renderCatalog(view()), false, true],
    ],
    rider: [
      ["Dashboard", "#/r-dashboard", "dash", () => Rider.renderDashboard(view())],
      ["Offers", "#/r-offers", "bell", () => Rider.renderOffers(view())],
      ["My Deliveries", "#/r-deliveries", "truck", () => Rider.renderDeliveries(view())],
      ["Utilities", "#/utilities", "tools", () => Admin.renderCatalog(view()), false, true],
    ],
  };

  const TITLES = {
    "#/shop": "Medicine Store",
    "#/cart": "Cart",
    "#/checkout": "Checkout",
    "#/orders": "My Orders",
    "#/prescriptions": "Prescriptions",
    "#/addresses": "Addresses",
    "#/profile": "Profile",
    "#/ph-dashboard": "Pharmacy Dashboard",
    "#/ph-inventory": "Inventory",
    "#/ph-orders": "Incoming Orders",
    "#/ph-prescriptions": "Rx Verification",
    "#/ph-forecasts": "Forecasts",
    "#/r-dashboard": "Rider Dashboard",
    "#/r-offers": "Delivery Offers",
    "#/r-deliveries": "My Deliveries",
    "#/utilities": "Test Utilities — Catalog & Seeder",
  };

  function view() { return document.getElementById("view"); }

  const ICONS = {
    shop: "▤", cart: "▣", orders: "≡", rx: "℞", addr: "⌂", profile: "☺",
    dash: "▦", inv: "▥", chart: "∿", bell: "♪", truck: "➤", tools: "⚒",
  };

  function navFor(role) {
    return routes[role] || [];
  }

  function renderShell() {
    const user = Session.user;
    document.getElementById("app").innerHTML = `
      <div class="layout">
        <aside class="sidebar">
          <div class="brand"><span class="brand-text">Medical<span>Panda</span></span><small>Web Test Console</small></div>
          <nav class="nav" id="nav"></nav>
          <div class="sidebar-foot">
            <div class="user-chip">
              <div class="avatar">${UI.esc((user.username || "?")[0].toUpperCase())}</div>
              <div class="meta">
                <div class="name">${UI.esc(user.username)}</div>
                <div class="role">${UI.esc(user.role)} · <a href="#" id="logout-link" style="color:#f87171">logout</a></div>
              </div>
            </div>
          </div>
        </aside>
        <main class="main">
          <header class="topbar">
            <h1 id="page-title"></h1>
            <span id="cart-slot"></span>
            <span class="badge teal mono" style="cursor:pointer" id="api-indicator" title="Click to change API base URL">${UI.esc(API.base())}</span>
          </header>
          <div class="content" id="view"></div>
        </main>
      </div>`;

    document.getElementById("logout-link").onclick = async (e) => {
      e.preventDefault();
      try { await API.post("/accounts/logout/", { refresh: Session.refresh }); } catch {}
      Pharmacy.stopPoll();
      Rider.stopPoll();
      Session.clear();
      UI.toast("Logged out");
      location.hash = "#/auth";
    };

    document.getElementById("api-indicator").onclick = () => {
      UI.modal(`<h3>API base URL</h3>
        <p class="hint" style="margin-bottom:12px">The console talks to this Django server. Same-origin by default.</p>
        <input class="input mono" id="api-base-modal" value="${UI.esc(API.base())}" />
        <div class="modal-actions">
          <button class="btn secondary" onclick="this.closest('.modal-backdrop').remove()">Cancel</button>
          <button class="btn" id="save-api-base">Save</button>
        </div>`, (backdrop) => {
        backdrop.querySelector("#save-api-base").onclick = () => {
          localStorage.setItem("mp_api_base", backdrop.querySelector("#api-base-modal").value.replace(/\/$/, "").trim());
          document.querySelector(".modal-backdrop").remove();
          renderShell();
          route();
        };
      });
    };

    buildNav();
    refreshCartBadge();
    if (typeof PandaAI !== 'undefined') PandaAI.init();
  }

  function buildNav() {
    const role = Session.role;
    const items = navFor(role);
    const current = (location.hash || "#/home").split("?")[0];
    document.getElementById("nav").innerHTML = `
      ${role === "customer" ? '<div class="nav-label">Shopping</div>' : ""}
      ${items.map(([label, href, icon]) => `
        ${label === "Utilities" ? '<div class="nav-label">Testing</div>' : ""}
        <a class="nav-item ${isActive(current, href) ? "active" : ""}" href="${href}">
          <span class="icon">${ICONS[icon] || "•"}</span><span class="label">${label}</span>
          ${href === "#/cart" ? '<span id="cart-badge" style="margin-left:auto"></span>' : ""}
        </a>`).join("")}
    `;
  }

  function isActive(current, href) {
    if (current === href) return true;
    if (href === "#/orders" && current.startsWith("#/orders")) return true;
    return false;
  }

  async function refreshCartBadge() {
    const el = document.getElementById("cart-badge");
    if (!el || !Session.access) return;
    try {
      const cart = await API.get("/customer/cart/");
      const count = (cart.items || []).filter((i) => i.quantity > 0).reduce((s, i) => s + i.quantity, 0);
      el.innerHTML = count ? `<span class="badge amber">${count}</span>` : "";
      const slot = document.getElementById("cart-slot");
      if (slot) slot.innerHTML = count ? `<a href="#/cart" class="badge amber" style="text-decoration:none">Cart · ${count}</a>` : "";
    } catch {}
  }

  function route() {
    const hash = location.hash || "#/home";

    if (!Session.access || !Session.user) {
      if (hash.startsWith("#/register")) Auth.renderRegister();
      else Auth.renderLogin();
      return;
    }
    if (hash === "#/auth" || hash === "#/login") { location.hash = "#/home"; return; }
    if (!document.getElementById("view")) renderShell();

    const role = Session.role;
    const base = hash.split("/").slice(0, 2).join("/");
    const rest = hash.split("/")[2];
    const items = navFor(role);

    let handler = null;
    if (base === "#/orders" && rest) {
      const pollHandle = {};
      handler = () => Customer.renderOrderDetail(view(), rest, pollHandle);
    } else {
      const match = items.find(([label, href]) => href === base);
      handler = match ? match[3] : null;
    }

    document.getElementById("page-title").textContent =
      TITLES[base] || (base === "#/orders" ? `Order #${rest}` : "");
    buildNav();
    refreshCartBadge();
    if (typeof PandaAI !== 'undefined') PandaAI.init();

    if (handler) handler();
    else {
      const first = items[0];
      if (first) { location.hash = first[1]; }
      else view().innerHTML = `<div class="banner error">Unknown home route for role "${UI.esc(role)}".</div>`;
    }
  }

  window.addEventListener("hashchange", () => {
    Pharmacy.stopPoll();
    Rider.stopPoll();
    route();
  });

  function boot() {
    if (!location.hash) location.hash = Session.access ? "#/home" : "#/auth";
    route();
  }

  boot();

  return { route, refreshCartBadge };
})();
