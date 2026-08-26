const UI = (() => {
  function esc(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
  }

  const ORDER_STATUS = {
    pending: ["Pending", "gray"],
    under_review: ["Under Review", "amber"],
    accepted: ["Accepted", "blue"],
    preparing: ["Preparing", "blue"],
    ready_for_pickup: ["Ready for Pickup", "amber"],
    picked_up: ["Picked Up", "teal"],
    on_the_way: ["On the Way", "teal"],
    delivered: ["Delivered", "green"],
    cancelled: ["Cancelled", "red"],
  };

  function statusBadge(status) {
    const [label, color] = ORDER_STATUS[status] || [status, "gray"];
    return `<span class="badge ${color}"><span class="dot"></span>${esc(label)}</span>`;
  }

  const STATUS_LABEL = (s) => (ORDER_STATUS[s] ? ORDER_STATUS[s][0] : s);

  function money(n) {
    const num = Number(n || 0);
    return `Rs ${num.toLocaleString("en-PK", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function toast(message, type = "") {
    const box = document.getElementById("toasts");
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.innerHTML = `<div>${esc(message)}</div>`;
    box.appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; }, 3800);
    setTimeout(() => el.remove(), 4200);
  }

  function errText(err) {
    return err && err.message ? err.message : "Something went wrong";
  }

  function toastErr(err) { toast(errText(err), "error"); }

  function modal(html, onMount) {
    const root = document.getElementById("modal-root");
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `<div class="modal">${html}</div>`;
    const close = () => backdrop.remove();
    backdrop.addEventListener("click", (e) => { if (e.target === backdrop) close(); });
    root.appendChild(backdrop);
    if (onMount) onMount(backdrop, close);
    return close;
  }

  function confirmModal(title, text, confirmLabel = "Confirm", danger = false) {
    return new Promise((resolve) => {
      modal(
        `<h3>${esc(title)}</h3><p style="color:var(--muted);font-size:14px">${esc(text)}</p>
         <div class="modal-actions">
           <button class="btn secondary" data-x="no">Cancel</button>
           <button class="btn ${danger ? "danger" : ""}" data-x="yes">${esc(confirmLabel)}</button>
         </div>`,
        (backdrop, close) => {
          backdrop.querySelector('[data-x="no"]').onclick = () => { close(); resolve(false); };
          backdrop.querySelector('[data-x="yes"]').onclick = () => { close(); resolve(true); };
        }
      );
    });
  }

  function field(label, inputHtml, hint = "") {
    return `<div class="field">
      <label>${esc(label)}</label>
      ${inputHtml}
      ${hint ? `<span class="hint">${esc(hint)}</span>` : ""}
    </div>`;
  }

  function emptyState(title, text) {
    return `<div class="empty"><b>${esc(title)}</b>${esc(text)}</div>`;
  }

  function loading() { return `<div class="loading-block"><div class="spinner"></div></div>`; }

  async function withLoading(container, fn) {
    container.innerHTML = loading();
    try {
      await fn();
    } catch (err) {
      container.innerHTML = `<div class="banner error">${esc(errText(err))}</div>`;
    }
  }

  function pager(page, count, pageSize, onPage) {
    const pages = Math.max(1, Math.ceil((count || 0) / pageSize));
    if (pages <= 1 && !count) return "";
    return `<div class="pager">
      <button class="btn sm secondary" ${page <= 1 ? "disabled" : ""} data-pg="${page - 1}">Prev</button>
      <span class="pg-info">Page ${page} of ${pages} · ${count ?? "?"} items</span>
      <button class="btn sm secondary" ${page >= pages ? "disabled" : ""} data-pg="${page + 1}">Next</button>
    </div>`;
  }

  function bindPager(container, onPage) {
    container.querySelectorAll("[data-pg]").forEach((b) => {
      b.onclick = () => onPage(parseInt(b.dataset.pg, 10));
    });
  }

  function mediaUrl(url) {
    if (!url) return "";
    if (url.startsWith("http")) return url;
    return API.base() + url;
  }

  return {
    esc, statusBadge, STATUS_LABEL, money, fmtDate, toast, toastErr, errText,
    modal, confirmModal, field, emptyState, loading, withLoading, pager, bindPager, mediaUrl,
  };
})();
