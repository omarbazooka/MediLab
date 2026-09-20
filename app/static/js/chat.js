(() => {
  const form = document.querySelector("#chat-form");
  if (!form) return;
  const input = document.querySelector("#chat-input");
  const sendButton = form.querySelector(".send-button");
  const messages = document.querySelector("#chat-messages");
  const errorBox = document.querySelector("#chat-error");
  const retryButton = document.querySelector("#retry-message");
  const typingTemplate = document.querySelector("#typing-template");
  let sending = false;
  let lastFailedMessage = "";

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  };
  const scrollLatest = () => messages.scrollTo({ top: messages.scrollHeight, behavior: "smooth" });
  const resizeInput = () => { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 130)}px`; sendButton.disabled = sending || !input.value.trim(); };
  const dispatchPrompt = (message) => { input.value = message; resizeInput(); form.requestSubmit(); };

  const addMessage = (role, content) => {
    document.querySelector("#welcome-state")?.remove();
    const article = el("article", `message message-${role}`);
    article.dataset.role = role;
    if (role === "assistant") {
      const avatar = el("div", "assistant-avatar");
      avatar.setAttribute("aria-hidden", "true");
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 24 24");
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", "M9 3h6v6h6v6h-6v6H9v-6H3V9h6V3Z"); svg.append(path); avatar.append(svg); article.append(avatar);
    }
    const stack = el("div", "message-stack");
    stack.append(el("div", "message-bubble", content)); article.append(stack); messages.append(article); scrollLatest();
    return stack;
  };

  const normalizeVisible = (payload) => {
    if (Array.isArray(payload.visible_results) && payload.visible_results.length) return payload.visible_results;
    const result = payload.structured_result || {};
    if (Array.isArray(result.packages)) return result.packages.map((item) => ({ ...item, item_type: "package" }));
    if (Array.isArray(result.branches)) return result.branches.map((item) => ({ ...item, item_type: "branch" }));
    if (result.test) return [{ ...result.test, item_type: "test" }];
    if (result.package) return [{ ...result.package, item_type: "package" }];
    return [];
  };

  const renderResults = (stack, items) => {
    if (!Array.isArray(items) || !items.length) return;
    const wrap = el("div", "structured-cards");
    items.forEach((item, index) => {
      const card = el("article", "result-card");
      card.append(el("span", "ordinal", item.position || index + 1));
      const content = el("div");
      const type = String(item.item_type || item.type || "service").toLowerCase();
      const name = item.name || item.test_name || item.branch_name || "MediLab service";
      content.append(el("h3", "", name));
      const details = item.sample_type || item.address || item.description || (item.tests ? `${item.tests.length} included tests` : "Verified catalog result");
      content.append(el("p", "", details)); card.append(content);
      if (item.price) card.append(el("span", "result-price", String(item.price)));
      const button = el("button", "", "Select"); button.type = "button";
      button.addEventListener("click", () => dispatchPrompt(`I choose the ${item.position || index + 1}${index === 0 ? "st" : index === 1 ? "nd" : index === 2 ? "rd" : "th"} option, ${name}.`));
      card.append(button); wrap.append(card);
    });
    stack.append(wrap);
  };

  const summaryLabels = { service_name: "Service", visit_type: "Visit", branch_name: "Branch", area: "Area", scheduled_date: "Date", scheduled_time: "Time", total_price: "Price", customer_name: "Customer", customer_phone: "Phone", address: "Address", booking_reference: "Reference" };
  const renderAction = (stack, action) => {
    if (!action || !action.status) return;
    const status = String(action.status).toUpperCase();
    const isSuccess = action.committed === true && action.success === true;
    const isCancellation = action.action_type === "CANCEL_BOOKING";
    const card = el("section", `action-card${isSuccess ? " success" : ""}${isCancellation && status === "AWAITING_CONFIRMATION" ? " danger" : ""}`);
    const header = el("div", "action-card-header"); header.append(el("span", "", isSuccess ? "✓" : isCancellation ? "!" : "▤"));
    header.append(el("strong", "", isSuccess ? (status === "CANCELLED" ? "Booking cancelled" : "Booking confirmed") : status === "AWAITING_CONFIRMATION" ? (isCancellation ? "Confirm cancellation" : "Booking summary") : status.includes("SLOT") ? "Choose another time" : "Booking details")); card.append(header);
    const summary = action.summary || {};
    if (action.booking_reference && !summary.booking_reference) summary.booking_reference = action.booking_reference;
    const list = el("dl", "action-summary");
    Object.entries(summaryLabels).forEach(([key, label]) => {
      if (summary[key] === undefined || summary[key] === null || summary[key] === "") return;
      const row = el("div"); row.append(el("dt", "", label)); let value = summary[key];
      if (key === "total_price" && !String(value).includes("EGP")) value = `${value} EGP`;
      row.append(el("dd", "", value)); list.append(row);
    });
    if (list.children.length) card.append(list);
    if (status === "AWAITING_CONFIRMATION") {
      const actions = el("div", "action-buttons");
      const confirm = el("button", "button button-primary button-small", isCancellation ? "Confirm cancellation" : "Confirm booking"); confirm.type = "button";
      confirm.addEventListener("click", () => dispatchPrompt(isCancellation ? "Yes, confirm the cancellation." : "Yes, confirm this booking.")); actions.append(confirm);
      const change = el("button", "button button-ghost button-small", isCancellation ? "Keep booking" : "Change details"); change.type = "button";
      change.addEventListener("click", () => dispatchPrompt(isCancellation ? "No, keep my booking." : "I need to change the booking details.")); actions.append(change); card.append(actions);
    }
    if ((status === "SLOT_ERROR" || status === "SLOT_FULL") && Array.isArray(action.alternatives)) {
      const alternatives = el("div", "alternative-slots");
      action.alternatives.forEach((slot) => { const button = el("button", "", slot.time || "Available time"); button.type = "button"; button.addEventListener("click", () => dispatchPrompt(`${slot.time} on ${slot.date} works for me.`)); alternatives.append(button); }); card.append(alternatives);
    }
    if (isSuccess && !isCancellation) {
      const actions = el("div", "action-buttons"); const statusLink = el("a", "button button-ghost button-small", "Check booking status"); statusLink.href = "/booking-status"; actions.append(statusLink); card.append(actions);
    }
    stack.append(card);
  };

  const renderPersisted = () => {
    document.querySelectorAll(".persisted-ui[data-metadata]").forEach((node) => {
      try { const metadata = JSON.parse(node.dataset.metadata); const stack = node.parentElement; renderResults(stack, metadata.visible_results || []); renderAction(stack, metadata.action_result); } catch (_) { /* Invalid legacy metadata is ignored. */ }
      node.remove();
    });
  };

  const setSending = (value) => { sending = value; messages.setAttribute("aria-busy", String(value)); sendButton.classList.toggle("loading", value); resizeInput(); };
  const showError = (message) => { errorBox.querySelector("p").textContent = message; errorBox.hidden = false; };
  const hideError = () => { errorBox.hidden = true; };

  const submit = async (message) => {
    if (sending || !message.trim()) return;
    hideError(); lastFailedMessage = message; addMessage("user", message); input.value = ""; resizeInput(); setSending(true);
    const typing = typingTemplate.content.cloneNode(true); messages.append(typing); scrollLatest();
    try {
      const response = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json", "Accept": "application/json" }, body: JSON.stringify({ message }) });
      const payload = await response.json().catch(() => ({})); document.querySelector(".typing-message")?.remove();
      if (!response.ok) throw new Error(payload.error?.message || "MediLab AI is temporarily unavailable. Please try again.");
      const stack = addMessage("assistant", payload.response); renderResults(stack, normalizeVisible(payload)); renderAction(stack, payload.action_result); lastFailedMessage = "";
    } catch (error) { document.querySelector(".typing-message")?.remove(); input.value = message; resizeInput(); showError(error.message || "Your message could not be sent. Please try again."); }
    finally { setSending(false); input.focus(); scrollLatest(); }
  };

  form.addEventListener("submit", (event) => { event.preventDefault(); submit(input.value.trim()); });
  input.addEventListener("input", resizeInput);
  input.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); } });
  retryButton.addEventListener("click", () => submit(lastFailedMessage || input.value));
  document.querySelectorAll("[data-chat-prompt]").forEach((button) => button.addEventListener("click", () => dispatchPrompt(button.dataset.chatPrompt)));
  renderPersisted(); resizeInput();
  const initialPrompt = new URLSearchParams(window.location.search).get("prompt");
  if (initialPrompt && !document.querySelector(".message")) { input.value = initialPrompt; resizeInput(); }
  if (document.querySelector(".message")) scrollLatest();
})();
