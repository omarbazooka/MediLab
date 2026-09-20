(() => {
  const form = document.querySelector("#status-form"); if (!form) return;
  const feedback = document.querySelector("#status-feedback"); const button = form.querySelector("button");
  const add = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
  const renderBooking = (booking) => {
    feedback.textContent = "";
    const card = add("article", "booking-result");
    const heading = add("div", "booking-result-heading"); heading.append(add("h3", "", "Booking details")); heading.append(add("span", `booking-status status-${String(booking.status).toLowerCase()}`, booking.status)); card.append(heading);
    const rows = { Reference: booking.reference, Service: booking.items, Visit: booking.visit_type, Branch: booking.branch_name, Date: booking.scheduled_date, Time: booking.scheduled_time, Price: booking.total_price ? `${booking.total_price} EGP` : null };
    const list = add("dl", "booking-result-grid"); Object.entries(rows).forEach(([label, value]) => { if (!value) return; const row = add("div"); row.append(add("dt", "", label)); row.append(add("dd", "", value)); list.append(row); }); card.append(list);
    if (String(booking.status).toUpperCase() !== "CANCELLED") { const cancel = add("a", "button button-ghost button-small", "Cancel this booking"); cancel.href = `/chat?prompt=${encodeURIComponent(`I want to cancel booking ${booking.reference}`)}`; card.append(cancel); }
    feedback.append(card);
  };
  form.addEventListener("submit", async (event) => {
    event.preventDefault(); feedback.className = "status-feedback"; feedback.textContent = "Checking your booking…"; button.disabled = true;
    const data = new FormData(form); const message = `Check booking status for reference ${data.get("reference")} using phone ${data.get("phone")}.`;
    try { const response = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) }); const payload = await response.json(); if (!response.ok) throw new Error(payload.error?.message || "Booking lookup is unavailable."); const booking = payload.action_result?.booking; if (booking) renderBooking(booking); else feedback.textContent = payload.response; }
    catch (error) { feedback.className = "status-feedback error"; feedback.textContent = error.message || "We could not check that booking. Please try again."; }
    finally { button.disabled = false; }
  });
})();
