(() => {
  const form = document.querySelector("#status-form"); if (!form) return;
  const feedback = document.querySelector("#status-feedback"); const button = form.querySelector("button");
  form.addEventListener("submit", async (event) => {
    event.preventDefault(); feedback.className = "status-feedback"; feedback.textContent = "Checking your booking…"; button.disabled = true;
    const data = new FormData(form); const message = `Check booking status for reference ${data.get("reference")} using phone ${data.get("phone")}.`;
    try { const response = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) }); const payload = await response.json(); if (!response.ok) throw new Error(payload.error?.message || "Booking lookup is unavailable."); feedback.textContent = payload.response; }
    catch (error) { feedback.className = "status-feedback error"; feedback.textContent = error.message || "We could not check that booking. Please try again."; }
    finally { button.disabled = false; }
  });
})();
