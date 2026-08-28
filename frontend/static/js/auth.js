const Auth = (() => {
  let pendingEmail = "";
  let selectedRole = "customer";
  let lastRegPayload = null;

  function page(title, bodyHtml) {
    return `
      <div class="auth-wrap">
        <div class="auth-card">
          <div class="auth-logo">Medical<span>Panda</span></div>
          <div class="auth-sub">${title}</div>
          ${bodyHtml}
        </div>
      </div>`;
  }

  function apiBaseField() {
    const current = localStorage.getItem("mp_api_base") || location.origin;
    return `<details style="margin-top:14px">
      <span class="hint">Advanced</span>
      <div class="field" style="margin-top:6px">
        <label>API base URL</label>
        <input class="input mono" id="api-base" value="${UI.esc(current)}" />
      </div>
    </details>`;
  }

  function renderLogin(msg = "") {
    document.getElementById("app").innerHTML = page("Log in to your account", `
      <form id="login-form">
        <div class="banner error" id="auth-error" style="display:${msg ? "block" : "none"}">${UI.esc(msg)}</div>
        <div class="field"><label>Account type</label><select class="input" name="role" required>
          <option value="customer">Customer</option>
          <option value="pharmacy">Pharmacy</option>
          <option value="rider">Rider</option>
        </select></div>
        <div class="field"><label>Email</label><input class="input" name="email" type="email" required placeholder="you@example.com" /></div>
        <div class="field"><label>Password</label><input class="input" name="password" type="password" required placeholder="••••••••" /></div>
        <button class="btn block" type="submit" id="login-btn">Log In</button>
      </form>
      <div class="auth-switch">New here? <a href="#/register">Create an account</a></div>
      ${apiBaseField()}
    `);

    document.getElementById("api-base").addEventListener("change", (e) => {
      localStorage.setItem("mp_api_base", e.target.value.replace(/\/$/, "").trim());
    });

    document.getElementById("login-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      const btn = document.getElementById("login-btn");
      btn.disabled = true;
      btn.textContent = "Logging in...";
      try {
        const data = await API.post("/accounts/login/", {
          email: f.email.value.trim(),
          password: f.password.value,
          role: f.role.value,
        });
        Session.save(data);
        UI.toast(`Welcome back, ${data.user.username}!`, "success");
        location.hash = "#/home";
      } catch (err) {
        renderLogin(UI.errText(err));
      }
    });
  }

  function renderRegister(msg = "") {
    const roles = [
      { id: "customer", icon: "R", label: "Customer" },
      { id: "pharmacy", icon: "P", label: "Pharmacy" },
      { id: "rider", icon: "D", label: "Rider" },
    ];
    document.getElementById("app").innerHTML = page("Create your account", `
      <form id="reg-form">
        <div class="banner error" style="display:${msg ? "block" : "none"}">${UI.esc(msg)}</div>
        <div class="role-picker">
          ${roles.map((r) => `
            <div class="role-opt ${selectedRole === r.id ? "selected" : ""}" data-role="${r.id}">
              <span class="r-icon">${r.icon}</span>${r.label}
            </div>`).join("")}
        </div>
        <div class="form-row">
          <div class="field"><label>First name</label><input class="input" name="first_name" /></div>
          <div class="field"><label>Last name</label><input class="input" name="last_name" /></div>
        </div>
        <div class="field"><label>Username</label><input class="input" name="username" required /></div>
        <div class="field"><label>Email</label><input class="input" name="email" type="email" required /></div>
        <div class="field"><label>Phone number</label><input class="input" name="phone_number" required placeholder="+92300..." /></div>
        <div class="field">
          <label>Password</label>
          <input class="input" name="password" type="password" required minlength="8" />
          <span class="hint">Min 8 characters, not all digits, not a common password.</span>
        </div>
        <button class="btn block" type="submit" id="reg-btn">Sign Up — Get OTP Code</button>
      </form>
      <div class="auth-switch">Already registered? <a href="#/login">Log in</a></div>
      ${apiBaseField()}
    `);

    document.getElementById("api-base").addEventListener("change", (e) => {
      localStorage.setItem("mp_api_base", e.target.value.replace(/\/$/, "").trim());
    });

    document.querySelectorAll(".role-opt").forEach((el) => {
      el.onclick = () => {
        selectedRole = el.dataset.role;
        document.querySelectorAll(".role-opt").forEach((o) => o.classList.toggle("selected", o === el));
      };
    });

    document.getElementById("reg-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      const btn = document.getElementById("reg-btn");
      btn.disabled = true;
      btn.textContent = "Sending OTP...";
      try {
        lastRegPayload = {
          username: f.username.value.trim(),
          email: f.email.value.trim(),
          password: f.password.value,
          role: selectedRole,
          phone_number: f.phone_number.value.trim(),
          first_name: f.first_name.value.trim(),
          last_name: f.last_name.value.trim(),
        };
        await API.post("/accounts/register/", lastRegPayload);
        pendingEmail = f.email.value.trim();
        renderOtp();
      } catch (err) {
        renderRegister(UI.errText(err));
      }
    });
  }

  function renderOtp(msg = "") {
    document.getElementById("app").innerHTML = page("Check your inbox", `
      <p style="text-align:center;color:var(--muted);font-size:13.5px;margin-bottom:16px">
        We sent a 6-digit verification code to<br /><b>${UI.esc(pendingEmail)}</b><br />
        <span class="hint">The code expires in 5 minutes.</span>
      </p>
      <form id="otp-form">
        <div class="banner error" style="display:${msg ? "block" : "none"}">${UI.esc(msg)}</div>
        <div class="field"><input class="input otp-input" name="code" maxlength="6" pattern="\\d{6}" placeholder="000000" autocomplete="one-time-code" required /></div>
        <button class="btn block" type="submit" id="otp-btn">Verify &amp; Create Account</button>
      </form>
      <div class="btn-group" style="margin-top:14px;justify-content:center">
        <button class="btn sm secondary" id="resend-btn">Resend code</button>
        <button class="btn sm ghost" id="back-btn">Back</button>
      </div>
    `);

    document.getElementById("otp-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = document.getElementById("otp-btn");
      btn.disabled = true;
      btn.textContent = "Verifying...";
      try {
        const data = await API.post("/accounts/register/verify/", {
          email: pendingEmail,
          role: lastRegPayload.role,
          code: e.target.code.value.trim(),
        });
        Session.save(data);
        UI.toast(`Account created — welcome, ${data.user.username}!`, "success");
        location.hash = "#/home";
      } catch (err) {
        renderOtp(UI.errText(err));
      }
    });

    document.getElementById("resend-btn").onclick = async () => {
      if (!lastRegPayload) { renderOtp("No registration data to resend — go back and sign up again."); return; }
      const btn = document.getElementById("resend-btn");
      btn.disabled = true;
      try {
        await API.post("/accounts/register/", lastRegPayload);
        UI.toast("A fresh code was sent to your email.", "success");
      } catch (err) {
        UI.toastErr(err);
      }
      btn.disabled = false;
    };

    document.getElementById("back-btn").onclick = () => renderRegister();
  }

  return { renderLogin, renderRegister, renderOtp };
})();
