/**
 * UI Utilities, Notifications, Modals, and Formatting
 */
const UI = {
  formatINR(amount) {
    const val = parseFloat(amount) || 0;
    return "₹" + val.toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  },

  formatDate(dateStr) {
    if (!dateStr) return "-";
    try {
      const parts = dateStr.split(" ")[0].split("-");
      if (parts.length === 3) {
        const year = parts[0];
        const month = parts[1];
        const day = parts[2];
        const d = new Date(year, month - 1, day);
        return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
      }
      return dateStr;
    } catch (e) {
      return dateStr;
    }
  },

  showToast(message, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "toast-container";
      document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    
    let icon = "🔔";
    if (type === "success") icon = "✅";
    if (type === "error") icon = "⚠️";
    if (type === "warning") icon = "⚡";

    toast.innerHTML = `
      <span class="toast-icon">${icon}</span>
      <span class="toast-message">${message}</span>
      <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
    `;

    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add("toast-fadeout");
      setTimeout(() => toast.remove(), 400);
    }, 4500);
  },

  confirm(title, message, onConfirm) {
    let modal = document.getElementById("confirm-modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "confirm-modal";
      modal.className = "modal-overlay";
      document.body.appendChild(modal);
    }

    modal.innerHTML = `
      <div class="modal-card">
        <div class="modal-header">
          <h3>${title}</h3>
          <button class="modal-close" onclick="document.getElementById('confirm-modal').classList.remove('active')">&times;</button>
        </div>
        <div class="modal-body">
          <p>${message}</p>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" onclick="document.getElementById('confirm-modal').classList.remove('active')">Cancel</button>
          <button class="btn btn-danger" id="confirm-modal-action-btn">Confirm</button>
        </div>
      </div>
    `;

    modal.classList.add("active");
    const actionBtn = document.getElementById("confirm-modal-action-btn");
    actionBtn.onclick = () => {
      modal.classList.remove("active");
      onConfirm();
    };
  },

  getPaymentBadge(status) {
    const s = String(status || "").toLowerCase();
    if (s === "paid") return `<span class="badge badge-paid">Paid</span>`;
    if (s === "partially paid") return `<span class="badge badge-partial">Partially Paid</span>`;
    return `<span class="badge badge-unpaid">Not Paid</span>`;
  },

  getVerificationBadge(status) {
    const s = String(status || "").toLowerCase();
    if (s === "verified") return `<span class="badge badge-verified">Verified</span>`;
    if (s === "rejected") return `<span class="badge badge-rejected">Rejected</span>`;
    return `<span class="badge badge-pending">Pending Verification</span>`;
  },

  async checkSystemHealth(elementId = "system-status-pill") {
    const el = document.getElementById(elementId);
    if (!el) return;

    try {
      const res = await API.get("/api/system/status");
      if (res.success && res.status) {
        if (res.status.connected) {
          el.innerHTML = `<span class="status-indicator online"></span> Google Sheets Connected`;
          el.className = "system-pill pill-online";
          el.title = `Spreadsheet ID: ${res.status.spreadsheet_id}`;
        } else {
          el.innerHTML = `<span class="status-indicator warning"></span> Local Storage (Setup Pending)`;
          el.className = "system-pill pill-warning";
          el.title = res.status.error || "Provide service account credentials in settings/env to connect to live Sheets.";
        }
      }
    } catch (e) {
      el.innerHTML = `<span class="status-indicator offline"></span> Backend Offline`;
      el.className = "system-pill pill-offline";
    }
  }
};

window.UI = UI;
