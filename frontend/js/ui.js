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
    // Also initialize Admin header and permissions
    this.initAdminHeader();

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
  },

  initAdminHeader() {
    if (typeof Auth === "undefined" || !Auth.isLoggedIn()) return;
    const user = Auth.getUser();
    if (!user || user.role !== "admin") return;

    const isMaster = Auth.isMasterAdmin();
    const currentPath = window.location.pathname.toLowerCase();
    const masterOnlyPages = ["subadmins.html", "settings.html", "cake-settings.html", "custom-fields.html"];
    
    if (!isMaster && masterOnlyPages.some(p => currentPath.includes(p))) {
      alert("Access Restricted: Only the Master Administrator can access this page.");
      window.location.href = "dashboard.html";
      return;
    }

    // Topbar identity update
    const topbarRight = document.querySelector(".topbar-right");
    if (topbarRight) {
      let identityDiv = document.getElementById("admin-identity-badge");
      if (!identityDiv) {
        const allDivs = topbarRight.querySelectorAll("div");
        for (let d of allDivs) {
          if (d.textContent.includes("Administrator") || d.textContent.includes("Admin") || d.textContent.includes("🛡️")) {
            identityDiv = d;
            identityDiv.id = "admin-identity-badge";
            break;
          }
        }
      }
      if (identityDiv) {
        if (isMaster) {
          identityDiv.innerHTML = `<span style="background: #E8F5E9; color: #1B5E20; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 0.85rem; border: 1px solid #C8E6C9; display: inline-flex; align-items: center; gap: 5px;">👑 Master Administrator</span>`;
        } else {
          identityDiv.innerHTML = `<span style="background: #EDE7F6; color: #4A148C; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 0.85rem; border: 1px solid #D1C4E9; display: inline-flex; align-items: center; gap: 5px;">🛡️ Subadmin: ${user.name || user.id}</span>`;
        }
      }
    }

    // Sidebar navigation adaptation
    const navList = document.querySelector(".sidebar-nav");
    if (navList) {
      // Add Subadmins link for Master Admin if not present
      if (isMaster && !document.getElementById("nav-subadmins")) {
        const subLi = document.createElement("li");
        subLi.className = "sidebar-nav-item";
        subLi.id = "nav-subadmins";
        if (currentPath.includes("subadmins.html")) subLi.classList.add("active");
        subLi.innerHTML = `<a href="subadmins.html"><span class="nav-icon">👥</span> Subadmins (4)</a>`;
        
        const settingsLi = navList.querySelector('a[href="settings.html"]')?.closest("li");
        if (settingsLi) {
          navList.insertBefore(subLi, settingsLi);
        } else {
          navList.appendChild(subLi);
        }
      }

      // If Subadmin, hide Master-only configuration tabs
      if (!isMaster) {
        const hideLinks = ["subadmins.html", "settings.html", "cake-settings.html", "custom-fields.html"];
        hideLinks.forEach(href => {
          const item = navList.querySelector(`a[href="${href}"]`)?.closest("li");
          if (item) item.style.display = "none";
        });
      }
    }
  }
};

window.UI = UI;
