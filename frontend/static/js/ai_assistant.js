const PandaAI = (() => {
  let panel = null;
  let isOpen = false;
  let isListening = false;
  let voiceEnabled = true;
  let currentConversationId = null;
  let recognition = null;
  let synth = window.speechSynthesis;
  let isSpeaking = false;
  let currentLang = "en-US";

  // AI Call Mode
  let callOverlay = null;
  let isCallActive = false;
  let callListening = false;
  let callRecognition = null;
  let autoListenTimer = null;

  function init() {
    if (Session.role !== "customer") return;
    injectToggle();
    injectCallButton();
    createPanel();
    createCallOverlay();
    initSpeechRecognition();
    initCallRecognition();
    if (synth) { synth.onvoiceschanged = () => synth.getVoices(); synth.getVoices(); }
  }

  function injectToggle() {
    const topbar = document.querySelector(".topbar");
    if (!topbar || document.getElementById("ai-toggle-btn")) return;
    const btn = document.createElement("button");
    btn.id = "ai-toggle-btn";
    btn.className = "ai-toggle";
    btn.innerHTML = '<span class="ai-toggle-icon">\u2728</span> <span>AI Chat</span>';
    btn.onclick = toggle;
    topbar.insertBefore(btn, topbar.querySelector("#api-indicator"));
  }

  function injectCallButton() {
    const topbar = document.querySelector(".topbar");
    if (!topbar || document.getElementById("ai-call-btn")) return;
    const btn = document.createElement("button");
    btn.id = "ai-call-btn";
    btn.className = "ai-call-btn";
    btn.title = "Call Panda AI";
    btn.innerHTML = '<span class="ai-call-icon">\ud83d\udcde</span>';
    btn.onclick = startCall;
    const toggleBtn = document.getElementById("ai-toggle-btn");
    if (toggleBtn) topbar.insertBefore(btn, toggleBtn.nextSibling);
    else topbar.insertBefore(btn, topbar.querySelector("#api-indicator"));
  }

  function toggle() { isOpen ? closePanel() : openPanel(); }

  function openPanel() {
    if (!panel) createPanel();
    panel.classList.add("open");
    isOpen = true;
    const btn = document.getElementById("ai-toggle-btn");
    if (btn) btn.classList.add("active");
    if (!panel.querySelector(".ai-msg")) {
      addBotMessage("Hi! I'm Panda, your AI medical assistant. I can help you find medicines, add them to your cart, and place orders. Just tell me what you need, or click the mic to talk to me!");
    }
    const input = panel.querySelector("#ai-input");
    if (input) setTimeout(() => input.focus(), 300);
  }

  function closePanel() {
    if (panel) panel.classList.remove("open");
    isOpen = false;
    const btn = document.getElementById("ai-toggle-btn");
    if (btn) btn.classList.remove("active");
    stopListening();
    stopSpeaking();
  }

  // Panel DOM
  function createPanel() {
    if (panel) return;
    panel = document.createElement("div");
    panel.className = "ai-panel";
    panel.innerHTML = `
      <div class="ai-header">
        <div class="ai-header-left">
          <div class="ai-avatar">\ud83d\udc3c</div>
          <div>
            <div class="ai-name">Panda AI</div>
            <div class="ai-status" id="ai-status">Ready to help</div>
          </div>
        </div>
        <div class="ai-header-right">
          <select class="ai-lang-select" id="ai-lang-select" title="Language">
            <option value="en-US">EN</option>
            <option value="ur-PK">\u0627\u0631\u062f\u0648</option>
          </select>
          <button class="ai-hdr-btn" id="ai-voice-toggle" title="Toggle voice">\ud83d\udd0a</button>
          <button class="ai-hdr-btn" id="ai-new-chat" title="New chat">\u2795</button>
          <button class="ai-hdr-btn" id="ai-close" title="Close">\u2715</button>
        </div>
      </div>
      <div class="ai-messages" id="ai-messages"></div>
      <div class="ai-input-area">
        <div class="ai-input-row">
          <button class="ai-mic-btn" id="ai-mic" title="Talk to Panda">\ud83c\udf99\ufe0f</button>
          <input type="text" id="ai-input" class="ai-input" placeholder="Ask me anything about medicines..." autocomplete="off" />
          <button class="ai-send-btn" id="ai-send" title="Send">\u27A4</button>
        </div>
        <div class="ai-input-hint" id="ai-input-hint"></div>
      </div>`;
    document.body.appendChild(panel);

    document.getElementById("ai-close").onclick = closePanel;
    document.getElementById("ai-send").onclick = sendMessage;
    document.getElementById("ai-mic").onclick = toggleListening;
    document.getElementById("ai-voice-toggle").onclick = toggleVoice;
    document.getElementById("ai-new-chat").onclick = newChat;
    document.getElementById("ai-lang-select").onchange = (e) => {
      currentLang = e.target.value;
      if (recognition) recognition.lang = currentLang;
      const callLang = document.getElementById("ai-call-lang");
      if (callLang) callLang.value = currentLang;
    };

    const input = panel.querySelector("#ai-input");
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    input.addEventListener("focus", () => stopSpeaking());
  }

  // AI Call Mode (Full-screen voice conversation)
  function createCallOverlay() {
    if (callOverlay) return;
    callOverlay = document.createElement("div");
    callOverlay.className = "ai-call-overlay";
    callOverlay.innerHTML = `
      <div class="ai-call-bg"></div>
      <div class="ai-call-content">
        <div class="ai-call-top">
          <div class="ai-call-top-left">
            <select class="ai-call-lang" id="ai-call-lang">
              <option value="en-US">English</option>
              <option value="ur-PK">\u0627\u0631\u062f\u0648 (Urdu)</option>
            </select>
          </div>
          <div class="ai-call-top-right">
            <button class="ai-call-text-toggle" id="ai-call-text-toggle" title="Show transcript">\ud83d\udcac</button>
          </div>
        </div>
        <div class="ai-call-center">
          <div class="ai-call-orb-wrap">
            <div class="ai-call-orb" id="ai-call-orb">
              <div class="ai-call-orb-inner">\ud83d\udc3c</div>
              <div class="ai-call-orb-ring ai-call-orb-ring-1"></div>
              <div class="ai-call-orb-ring ai-call-orb-ring-2"></div>
              <div class="ai-call-orb-ring ai-call-orb-ring-3"></div>
            </div>
          </div>
          <div class="ai-call-state" id="ai-call-state">Tap the orb to speak</div>
          <div class="ai-call-live-text" id="ai-call-live-text"></div>
        </div>
        <div class="ai-call-transcript" id="ai-call-transcript">
          <div class="ai-call-transcript-inner" id="ai-call-transcript-inner"></div>
        </div>
        <div class="ai-call-bottom">
          <button class="ai-call-mute-btn" id="ai-call-mute" title="Mute voice">\ud83d\udd0a</button>
          <button class="ai-call-end-btn" id="ai-call-end" title="End call">
            <span class="ai-call-end-icon">\ud83d\udcde</span>
          </button>
        </div>
      </div>`;
    document.body.appendChild(callOverlay);

    document.getElementById("ai-call-end").onclick = endCall;
    document.getElementById("ai-call-orb").onclick = toggleCallListening;
    document.getElementById("ai-call-mute").onclick = toggleCallMute;
    document.getElementById("ai-call-text-toggle").onclick = toggleCallTranscript;
    document.getElementById("ai-call-lang").onchange = (e) => {
      currentLang = e.target.value;
      if (callRecognition) callRecognition.lang = currentLang;
      const panelLang = panel ? panel.querySelector("#ai-lang-select") : null;
      if (panelLang) panelLang.value = currentLang;
    };
  }

  function startCall() {
    if (isCallActive) return;
    isCallActive = true;
    callOverlay.classList.add("active");
    setCallState("Tap the orb to speak");
    clearCallTranscript();
  }

  function endCall() {
    isCallActive = false;
    callListening = false;
    callOverlay.classList.remove("active");
    stopCallListening();
    stopSpeaking();
    clearTimeout(autoListenTimer);
  }

  function setCallState(text) {
    const el = document.getElementById("ai-call-state");
    if (el) el.textContent = text;
    const orb = document.getElementById("ai-call-orb");
    if (orb) {
      orb.classList.remove("listening", "thinking", "speaking");
      if (text.includes("Listening")) orb.classList.add("listening");
      else if (text.includes("Think") || text.includes("Process")) orb.classList.add("thinking");
      else if (text.includes("Speaking") || isSpeaking) orb.classList.add("speaking");
    }
  }

  function setCallLiveText(text) {
    const el = document.getElementById("ai-call-live-text");
    if (el) el.textContent = text || "";
  }

  function addToCallTranscript(role, text) {
    const inner = document.getElementById("ai-call-transcript-inner");
    if (!inner || !text) return;
    const div = document.createElement("div");
    div.className = "ai-call-tmsg " + (role === "user" ? "ai-call-tmsg-user" : "ai-call-tmsg-bot");
    div.innerHTML = '<span class="ai-call-tmsg-role">' + (role === "user" ? "You" : "Panda") + '</span>' + UI.esc(text);
    inner.appendChild(div);
    const container = document.getElementById("ai-call-transcript");
    if (container) container.scrollTop = container.scrollHeight;
  }

  function clearCallTranscript() {
    const inner = document.getElementById("ai-call-transcript-inner");
    if (inner) inner.innerHTML = "";
  }

  function toggleCallTranscript() {
    const el = document.getElementById("ai-call-transcript");
    if (el) el.classList.toggle("visible");
  }

  function toggleCallMute() {
    voiceEnabled = !voiceEnabled;
    if (!voiceEnabled) stopSpeaking();
    const btn = document.getElementById("ai-call-mute");
    if (btn) btn.textContent = voiceEnabled ? "\ud83d\udd0a" : "\ud83d\udd07";
  }

  // Call Speech Recognition
  function initCallRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    callRecognition = new SR();
    callRecognition.continuous = false;
    callRecognition.interimResults = true;
    callRecognition.lang = currentLang;

    callRecognition.onresult = (event) => {
      let transcript = "";
      let isFinal = false;
      for (let i = 0; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
        if (event.results[i].isFinal) isFinal = true;
      }
      setCallLiveText(transcript);
      if (isFinal && transcript.trim()) {
        stopCallListening();
        setCallState("Processing...");
        setCallLiveText("");
        sendCallMessage(transcript.trim());
      }
    };

    callRecognition.onerror = (event) => {
      stopCallListening();
      if (event.error !== "aborted") setCallState("Error: " + event.error + ". Tap orb to retry.");
    };

    callRecognition.onend = () => {
      if (callListening) {
        callListening = false;
        if (isCallActive) setCallState("Tap the orb to speak");
      }
    };
  }

  function toggleCallListening() {
    if (!isCallActive) return;
    callListening ? stopCallListening() : startCallListening();
  }

  function startCallListening() {
    if (!callRecognition) { setCallState("Voice not supported. Use Chrome."); return; }
    stopSpeaking();
    clearTimeout(autoListenTimer);
    callListening = true;
    callRecognition.lang = currentLang;
    setCallState("Listening...");
    setCallLiveText("");
    try { callRecognition.start(); } catch (e) {
      callListening = false;
      try { callRecognition.stop(); } catch (e2) {}
      setTimeout(() => {
        try { callRecognition.start(); callListening = true; } catch (e3) { setCallState("Tap orb to retry"); }
      }, 200);
    }
  }

  function stopCallListening() {
    callListening = false;
    if (callRecognition) try { callRecognition.stop(); } catch (e) {}
  }

  function sendCallMessage(text) {
    addToCallTranscript("user", text);
    setCallState("Thinking...");
    API.post("/ai/chat/", { message: text, conversation_id: currentConversationId })
      .then((data) => {
        currentConversationId = data.conversation_id;
        addToCallTranscript("bot", data.reply);
        setCallState("Speaking...");
        speakCall(data.reply, () => {
          if (isCallActive) {
            setCallState("Tap the orb to speak");
            autoListenTimer = setTimeout(() => {
              if (isCallActive && !callListening && !isSpeaking) startCallListening();
            }, 1500);
          }
        });
        processActions(data.actions || []);
        if (isOpen && panel) addBotMessage(data.reply, data.actions || []);
      })
      .catch((err) => {
        setCallState("Error. Tap orb to try again.");
        addToCallTranscript("bot", "Sorry, something went wrong.");
      });
  }

  function speakCall(text, onEnd) {
    if (!voiceEnabled || !synth) { if (onEnd) onEnd(); return; }
    stopSpeaking();
    const clean = text.replace(/[*_`#]/g, "").replace(/\{[^}]*\}/g, "").replace(/Rs\s?(\d+)/g, "$1 rupees");
    if (clean.length < 3) { if (onEnd) onEnd(); return; }
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.rate = 1.05;
    utterance.pitch = 1.05;
    const voices = synth.getVoices();
    let preferred = null;
    if (currentLang.startsWith("ur")) {
      preferred = voices.find((v) => v.lang.startsWith("ur"))
        || voices.find((v) => v.lang.startsWith("hi"))
        || voices.find((v) => v.lang.startsWith("en") && v.name.includes("Female"));
      utterance.lang = "ur-PK";
    } else {
      preferred = voices.find((v) => v.lang.startsWith("en") && v.name.includes("Female"))
        || voices.find((v) => v.lang.startsWith("en") && v.name.includes("Google"))
        || voices.find((v) => v.lang.startsWith("en"));
      utterance.lang = "en-US";
    }
    if (preferred) utterance.voice = preferred;
    utterance.onstart = () => { isSpeaking = true; setCallState("Speaking..."); };
    utterance.onend = () => { isSpeaking = false; if (onEnd) onEnd(); };
    utterance.onerror = () => { isSpeaking = false; if (onEnd) onEnd(); };
    synth.speak(utterance);
  }

  // Chat Panel Speech Recognition
  function initSpeechRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    recognition = new SR();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = currentLang;
    recognition.onresult = (event) => {
      const input = panel.querySelector("#ai-input");
      let transcript = "";
      for (let i = 0; i < event.results.length; i++) transcript += event.results[i][0].transcript;
      input.value = transcript;
      if (event.results[event.results.length - 1].isFinal) {
        stopListening();
        if (transcript.trim()) sendMessage();
      }
    };
    recognition.onerror = (event) => {
      stopListening();
      if (event.error !== "aborted") setHint("Voice error: " + event.error);
    };
    recognition.onend = () => { if (isListening) stopListening(); };
  }

  function toggleListening() { isListening ? stopListening() : startListening(); }

  function startListening() {
    if (!recognition) { setHint("Speech recognition not supported. Try Chrome."); return; }
    stopSpeaking();
    isListening = true;
    const mic = panel.querySelector("#ai-mic");
    mic.classList.add("listening");
    setStatus("Listening...");
    setHint("Speak now...");
    panel.querySelector("#ai-input").value = "";
    try { recognition.start(); } catch (e) { stopListening(); }
  }

  function stopListening() {
    isListening = false;
    const mic = panel ? panel.querySelector("#ai-mic") : null;
    if (mic) mic.classList.remove("listening");
    if (recognition) try { recognition.stop(); } catch (e) {}
    if (panel) { setStatus("Ready to help"); setHint(""); }
  }

  // Speech Synthesis for Chat Panel
  function speak(text) {
    if (!voiceEnabled || !synth) return;
    stopSpeaking();
    const clean = text.replace(/[*_`#]/g, "").replace(/\{[^}]*\}/g, "").replace(/Rs\s?(\d+)/g, "$1 rupees");
    if (clean.length < 3) return;
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.rate = 1.05; utterance.pitch = 1.05;
    const voices = synth.getVoices();
    let preferred = null;
    if (currentLang.startsWith("ur")) {
      preferred = voices.find((v) => v.lang.startsWith("ur")) || voices.find((v) => v.lang.startsWith("hi")) || voices.find((v) => v.lang.startsWith("en") && v.name.includes("Female"));
      utterance.lang = "ur-PK";
    } else {
      preferred = voices.find((v) => v.lang.startsWith("en") && v.name.includes("Female")) || voices.find((v) => v.lang.startsWith("en") && v.name.includes("Google")) || voices.find((v) => v.lang.startsWith("en"));
      utterance.lang = "en-US";
    }
    if (preferred) utterance.voice = preferred;
    utterance.onstart = () => { isSpeaking = true; updateVoiceBtn(); };
    utterance.onend = () => { isSpeaking = false; updateVoiceBtn(); };
    synth.speak(utterance);
  }

  function stopSpeaking() { if (synth) synth.cancel(); isSpeaking = false; updateVoiceBtn(); }

  function toggleVoice() {
    voiceEnabled = !voiceEnabled;
    if (!voiceEnabled) stopSpeaking();
    updateVoiceBtn();
    UI.toast(voiceEnabled ? "Voice enabled" : "Voice disabled", "");
  }

  function updateVoiceBtn() {
    const btn = panel ? panel.querySelector("#ai-voice-toggle") : null;
    if (!btn) return;
    btn.textContent = voiceEnabled ? "\ud83d\udd0a" : "\ud83d\udd07";
    btn.classList.toggle("muted", !voiceEnabled);
    btn.classList.toggle("speaking", isSpeaking);
  }

  // Messaging (Chat Panel)
  function sendMessage() {
    const input = panel.querySelector("#ai-input");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    stopSpeaking();
    addUserMessage(text);
    showTyping();
    setStatus("Thinking...");
    API.post("/ai/chat/", { message: text, conversation_id: currentConversationId })
      .then((data) => {
        hideTyping();
        currentConversationId = data.conversation_id;
        addBotMessage(data.reply, data.actions || []);
        speak(data.reply);
        processActions(data.actions || []);
        setStatus("Ready to help");
      })
      .catch((err) => {
        hideTyping();
        addBotMessage("Sorry, I'm having trouble right now. " + UI.errText(err));
        setStatus("Error");
      });
  }

  function addUserMessage(text) {
    const box = panel.querySelector("#ai-messages");
    const el = document.createElement("div");
    el.className = "ai-msg ai-msg-user";
    el.innerHTML = '<div class="ai-bubble ai-bubble-user">' + UI.esc(text) + '</div>';
    box.appendChild(el);
    scrollBottom();
  }

  function addBotMessage(text, actions) {
    const box = panel.querySelector("#ai-messages");
    const el = document.createElement("div");
    el.className = "ai-msg ai-msg-bot";
    let html = UI.esc(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`(.+?)`/g, '<code class="ai-code">$1</code>')
      .replace(/\n/g, "<br>");
    let actionHtml = "";
    if (actions && actions.length > 0) actionHtml = renderActionCards(actions);
    el.innerHTML = '<div class="ai-bubble ai-bubble-bot"><div class="ai-bot-avatar">\ud83d\udc3c</div><div class="ai-bot-content">' + html + '</div></div>' + actionHtml;
    box.appendChild(el);
    scrollBottom();
    bindActionButtons(el);
  }

  function scrollBottom() {
    const box = panel.querySelector("#ai-messages");
    if (box) setTimeout(() => { box.scrollTop = box.scrollHeight; }, 50);
  }

  function showTyping() {
    const box = panel.querySelector("#ai-messages");
    const el = document.createElement("div");
    el.className = "ai-msg ai-msg-bot ai-typing-msg";
    el.innerHTML = '<div class="ai-bubble ai-bubble-bot"><div class="ai-bot-avatar">\ud83d\udc3c</div><div class="ai-typing"><span></span><span></span><span></span></div></div>';
    box.appendChild(el);
    scrollBottom();
  }

  function hideTyping() {
    const el = panel.querySelector(".ai-typing-msg");
    if (el) el.remove();
  }

  // Action cards
  function renderActionCards(actions) {
    let html = "";
    for (const action of actions) {
      const tool = action.tool;
      const result = action.result || {};
      if (tool === "search_medicines" && result.medicines) html += renderMedicineCards(result);
      else if (tool === "symptom_check") html += renderSymptomCard(result);
      else if (tool === "get_cart" && result.items) html += renderCartCard(result);
      else if (tool === "add_to_cart" && result.success) { html += renderSuccessCard(result.message || "Added to cart!"); App.refreshCartBadge(); }
      else if (tool === "remove_from_cart" && result.success) { html += renderSuccessCard(result.message || "Removed."); App.refreshCartBadge(); }
      else if (tool === "prepare_order" && result.ready) html += renderOrderPreview(result);
      else if (tool === "confirm_place_order" && result.success) { html += renderOrderPlacedCard(result); App.refreshCartBadge(); }
      else if (tool === "get_my_orders" && result.orders) html += renderOrdersCard(result);
      else if (tool === "get_order_status") html += renderOrderStatusCard(result);
      else if (tool === "get_my_addresses" && result.addresses) html += renderAddressesCard(result);
      else if (tool === "get_categories" && result.categories) html += renderCategoriesCard(result);
      else if (tool === "get_medicine_details") html += renderMedicineDetailCard(result);
      else if (tool === "get_user_profile") html += renderProfileCard(result);
    }
    return html;
  }

  function renderMedicineCardBody(result) {
    if (!result.medicines || result.medicines.length === 0) return '<div class="ai-empty">No medicines found.</div>';
    return result.medicines.map((m) => {
      const available = m.available && m.stock > 0;
      const stockLine = available
        ? '<div class="ai-med-price-line"><span class="ai-price">Rs ' + (m.price || 0).toLocaleString() + '</span><span class="ai-in-stock-badge">In stock \u00b7 ' + (m.stock || 0) + '</span></div>'
        : '<div class="ai-med-price-line"><span class="ai-out-badge">Not available</span></div>';
      const addBtn = available
        ? '<button class="ai-action-btn ai-add-btn" data-medicine-id="' + m.id + '" data-medicine-name="' + UI.esc(m.name) + '">+ Add</button>'
        : '<span class="ai-out-badge">Out of stock</span>';
      return '<div class="ai-med-item"><div class="ai-med-info"><div class="ai-med-name">' + UI.esc(m.name) + ' ' + UI.esc(m.strength || "") + '</div><div class="ai-med-sub">' + UI.esc(m.generic_name || "") + (m.form ? ' \u00b7 ' + UI.esc(m.form) : "") + (m.requires_prescription ? ' <span class="ai-rx-badge">Rx</span>' : ' <span class="ai-otc-badge">OTC</span>') + '</div>' + stockLine + (m.description ? '<div class="ai-med-desc">' + UI.esc(m.description.substring(0, 80)) + '</div>' : "") + '</div>' + addBtn + '</div>';
    }).join("");
  }

  function renderMedicineCards(result) {
    if (!result.medicines || result.medicines.length === 0) return '<div class="ai-action-card ai-empty">No medicines found.</div>';
    const items = renderMedicineCardBody(result);
    return '<div class="ai-action-card ai-med-list-card"><div class="ai-card-title">Found ' + result.found + ' medicine(s)' + (result.pharmacy ? ' \u2014 ' + UI.esc(result.pharmacy) : "") + '</div>' + items + '</div>';
  }

  function renderSymptomCard(result) {
    if (result.needs_clarification) {
      return '<div class="ai-action-card ai-symptom-card"><div class="ai-card-title">\ud83d\udca1 I need a bit more detail</div><div>' + UI.esc(result.question || result.follow_up_question || "Please describe your symptoms.") + '</div></div>';
    }
    let html = '<div class="ai-action-card ai-symptom-card"><div class="ai-card-title">\ud83e\ude7a ' + UI.esc(result.label) + '</div>';
    html += '<div class="ai-med-desc">' + UI.esc(result.advice) + '</div>';
    if (result.red_flag || result.doctor_visit) {
      html += '<div class="ai-risk high"><b>\u26a0\ufe0f See a doctor:</b> ' + UI.esc(result.red_flag || "A doctor visit is recommended for this condition.") + '</div>';
    }
    html += result.doctor_visit && !result.red_flag ? '' : '';
    if (result.follow_up_question) html += '<div class="hint" style="margin-top:6px">' + UI.esc(result.follow_up_question) + '</div>';
    if (result.medicines && result.medicines.length) {
      html += '<div class="ai-divider"></div><div class="ai-card-title" style="font-size:12px">Recommended medicines</div>' + renderMedicineCardBody(result);
    }
    html += '</div>';
    return html;
  }

  function renderCartCard(result) {
    if (!result.items || result.items.length === 0) return '<div class="ai-action-card ai-empty">Your cart is empty.</div>';
    const items = result.items.map((i) => '<div class="ai-cart-item"><span>' + UI.esc(i.medicine_name) + ' ' + UI.esc(i.strength || "") + ' \u00d7 ' + i.quantity + '</span><span class="ai-price">Rs ' + (i.line_total || 0).toLocaleString() + '</span></div>').join("");
    return '<div class="ai-action-card ai-cart-card"><div class="ai-card-title">\ud83d\uded2 Cart (' + result.item_count + ' items) \u2014 ' + UI.esc(result.pharmacy) + '</div>' + items + '<div class="ai-cart-total"><span>Subtotal</span><b>Rs ' + (result.subtotal || 0).toLocaleString() + '</b></div><div class="ai-card-actions"><button class="ai-action-btn ai-primary-btn" id="ai-go-checkout">Proceed to Checkout</button></div></div>';
  }

  function renderOrderPreview(result) {
    const items = result.items.map((i) => '<div class="ai-cart-item"><span>' + UI.esc(i.medicine_name) + ' ' + UI.esc(i.strength || "") + ' \u00d7 ' + i.quantity + '</span><span class="ai-price">Rs ' + (i.line_total || 0).toLocaleString() + '</span></div>').join("");
    return '<div class="ai-action-card ai-order-preview"><div class="ai-card-title">\ud83d\udccb Order Summary</div><div class="ai-order-meta"><div><span class="ai-meta-label">Pharmacy:</span> ' + UI.esc(result.pharmacy) + '</div><div><span class="ai-meta-label">Address:</span> ' + UI.esc(result.address) + '</div><div><span class="ai-meta-label">Payment:</span> ' + UI.esc(result.payment_method) + '</div></div><div class="ai-divider"></div>' + items + '<div class="ai-cart-total"><span>Total</span><b>Rs ' + (result.subtotal || 0).toLocaleString() + '</b></div><div class="ai-card-actions"><button class="ai-action-btn ai-confirm-btn" data-address-id="' + result.address_id + '" data-payment="' + UI.esc(result.payment_method) + '">\u2714 Confirm &amp; Place Order</button></div></div>';
  }

  function renderOrderPlacedCard(result) {
    return '<div class="ai-action-card ai-success-card"><div class="ai-success-icon">\u2705</div><div class="ai-card-title">Order #' + result.order_id + ' Placed!</div><div>Total: Rs ' + (result.total || 0).toLocaleString() + ' \u00b7 Status: ' + UI.esc(result.status) + '</div><div class="ai-card-actions"><button class="ai-action-btn ai-secondary-btn" data-view-order="' + result.order_id + '">View Order</button></div></div>';
  }

  function renderSuccessCard(message) { return '<div class="ai-action-card ai-mini-success">\u2705 ' + UI.esc(message) + '</div>'; }

  function renderOrdersCard(result) {
    if (!result.orders || result.orders.length === 0) return '<div class="ai-action-card ai-empty">No orders found.</div>';
    const items = result.orders.map((o) => '<div class="ai-order-row" data-view-order="' + o.id + '"><div><b>#' + o.id + '</b> ' + UI.statusBadge(o.status) + '</div><div class="ai-order-sub">' + o.items_count + ' items \u00b7 Rs ' + (o.total || 0).toLocaleString() + ' \u00b7 ' + UI.esc(o.pharmacy) + '</div><div class="ai-order-date">' + UI.fmtDate(o.created_at) + '</div></div>').join("");
    return '<div class="ai-action-card ai-orders-card"><div class="ai-card-title">\ud83d\udce6 Your Recent Orders (' + result.count + ')</div>' + items + '</div>';
  }

  function renderOrderStatusCard(result) {
    if (result.error) return '<div class="ai-action-card ai-error">' + UI.esc(result.error) + '</div>';
    const history = (result.status_history || []).map((h) => '<div class="ai-timeline-item"><div class="ai-tl-dot"></div><div><b>' + UI.esc(h.status) + '</b> <span class="ai-tl-time">' + UI.fmtDate(h.time) + '</span></div></div>').join("");
    return '<div class="ai-action-card ai-status-card"><div class="ai-card-title">Order #' + result.id + ' ' + UI.statusBadge(result.status) + '</div><div class="ai-order-meta"><div><span class="ai-meta-label">Total:</span> Rs ' + (result.total || 0).toLocaleString() + '</div><div><span class="ai-meta-label">Pharmacy:</span> ' + UI.esc(result.pharmacy) + '</div><div><span class="ai-meta-label">Address:</span> ' + UI.esc(result.address) + '</div></div><div class="ai-divider"></div><div class="ai-timeline">' + history + '</div></div>';
  }

  function renderAddressesCard(result) {
    if (!result.addresses || result.addresses.length === 0) return '<div class="ai-action-card ai-empty">No saved addresses.</div>';
    const items = result.addresses.map((a) => '<div class="ai-addr-item"><b>' + UI.esc(a.label) + '</b> ' + (a.is_default ? '<span class="ai-default-badge">Default</span>' : "") + '<div class="ai-addr-line">' + UI.esc(a.address_line) + ', ' + UI.esc(a.city) + '</div></div>').join("");
    return '<div class="ai-action-card ai-addr-card"><div class="ai-card-title">\ud83c\udfe0 Saved Addresses</div>' + items + '</div>';
  }

  function renderCategoriesCard(result) {
    const items = result.categories.map((c) => '<span class="ai-cat-chip">' + UI.esc(c.name) + '</span>').join("");
    return '<div class="ai-action-card ai-cat-card"><div class="ai-card-title">\ud83d\udcc1 Categories</div><div class="ai-cat-list">' + items + '</div></div>';
  }

  function renderMedicineDetailCard(result) {
    if (result.error) return '<div class="ai-action-card ai-error">' + UI.esc(result.error) + '</div>';
    const available = result.available && result.stock > 0;
    const stockRow = available
      ? '<div><span class="ai-meta-label">Stock:</span> <span class="ai-in-stock-badge">\u2713 In stock \u00b7 ' + result.stock + ' available</span></div>'
      : '<div><span class="ai-meta-label">Stock:</span> <span class="ai-out-badge">Not available at this pharmacy</span></div>';
    const addBtn = available
      ? '<div class="ai-card-actions"><button class="ai-action-btn ai-add-btn" data-medicine-id="' + result.id + '" data-medicine-name="' + UI.esc(result.name) + '">+ Add to Cart</button></div>'
      : '<div class="ai-card-actions"><button class="ai-action-btn" disabled>Out of stock</button></div>';
    return '<div class="ai-action-card ai-med-detail"><div class="ai-card-title">' + UI.esc(result.name) + ' ' + UI.esc(result.strength || "") + '</div><div class="ai-order-meta">' + (result.generic_name ? '<div><span class="ai-meta-label">Generic:</span> ' + UI.esc(result.generic_name) + '</div>' : "") + (result.brand ? '<div><span class="ai-meta-label">Brand:</span> ' + UI.esc(result.brand) + '</div>' : "") + (result.category ? '<div><span class="ai-meta-label">Category:</span> ' + UI.esc(result.category) + '</div>' : "") + '<div><span class="ai-meta-label">Form:</span> ' + UI.esc(result.form || "N/A") + '</div><div><span class="ai-meta-label">Price:</span> Rs ' + (result.price || 0).toLocaleString() + '</div>' + stockRow + '<div><span class="ai-meta-label">Pharmacy:</span> ' + UI.esc(result.pharmacy) + '</div></div>' + (result.description ? '<div class="ai-divider"></div><div class="ai-med-desc">' + UI.esc(result.description) + '</div>' : "") + addBtn + '</div>';
  }

  function renderProfileCard(result) {
    return '<div class="ai-action-card ai-profile-card"><div class="ai-card-title">\ud83d\udc64 Your Profile</div><div class="ai-order-meta"><div><span class="ai-meta-label">Username:</span> ' + UI.esc(result.username) + '</div><div><span class="ai-meta-label">Email:</span> ' + UI.esc(result.email) + '</div><div><span class="ai-meta-label">Phone:</span> ' + UI.esc(result.phone) + '</div><div><span class="ai-meta-label">Wallet:</span> Rs ' + (result.wallet_balance || 0).toLocaleString() + '</div></div></div>';
  }

  // Bind action buttons
  function bindActionButtons(container) {
    container.querySelectorAll(".ai-add-btn").forEach((btn) => {
      btn.onclick = async () => {
        const medId = Number(btn.dataset.medicineId);
        const medName = btn.dataset.medicineName || "";
        btn.disabled = true; btn.textContent = "Adding...";
        try {
          const data = await API.post("/ai/chat/", { message: "Add " + medName + " (ID: " + medId + ") to my cart with quantity 1", conversation_id: currentConversationId });
          currentConversationId = data.conversation_id;
          btn.textContent = "\u2714 Added"; btn.classList.add("done");
          addBotMessage(data.reply, data.actions || []); speak(data.reply); App.refreshCartBadge();
        } catch (err) { btn.disabled = false; btn.textContent = "+ Add"; UI.toastErr(err); }
      };
    });
    container.querySelectorAll(".ai-confirm-btn").forEach((btn) => {
      btn.onclick = async () => {
        btn.disabled = true; btn.textContent = "Placing order..."; setStatus("Placing order...");
        try {
          const data = await API.post("/ai/chat/", { message: "Yes, confirm and place the order now.", conversation_id: currentConversationId });
          currentConversationId = data.conversation_id; hideTyping();
          addBotMessage(data.reply, data.actions || []); speak(data.reply); setStatus("Ready to help");
        } catch (err) { btn.disabled = false; btn.textContent = "\u2714 Confirm & Place Order"; UI.toastErr(err); setStatus("Error"); }
      };
    });
    container.querySelectorAll("[data-view-order]").forEach((btn) => { btn.onclick = () => { location.hash = "#/orders/" + btn.dataset.viewOrder; closePanel(); }; });
    const checkoutBtn = container.querySelector("#ai-go-checkout");
    if (checkoutBtn) checkoutBtn.onclick = () => { location.hash = "#/checkout"; closePanel(); };
  }

  function processActions(actions) {
    for (const a of actions) {
      if (a.tool === "add_to_cart" || a.tool === "remove_from_cart" || a.tool === "confirm_place_order") App.refreshCartBadge();
    }
  }

  function newChat() {
    currentConversationId = null;
    const box = panel.querySelector("#ai-messages");
    if (box) box.innerHTML = "";
    addBotMessage("New chat started! How can I help you today?");
  }

  function setStatus(text) { const el = panel ? panel.querySelector("#ai-status") : null; if (el) el.textContent = text; }
  function setHint(text) { const el = panel ? panel.querySelector("#ai-input-hint") : null; if (el) el.textContent = text; }

  return { init, toggle, openPanel, closePanel, startCall, endCall };
})();
