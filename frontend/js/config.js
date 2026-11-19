/**
 * Configuration for Christmas Cake Challenge Application
 */
const CONFIG = {
  // If frontend is deployed separately on Vercel, the backend API URL can be set here or in localStorage
  get API_BASE_URL() {
    // 1. Check if configured in localStorage (easy for user/tester override)
    const stored = localStorage.getItem("API_BASE_URL");
    if (stored && stored.trim()) {
      return stored.trim().replace(/\/+$/, "");
    }
    // 2. If running locally on a static server (e.g., port 3000, 8080, 5500), point to default Flask port 5000
    if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
      if (window.location.port !== "5000") {
        return "http://localhost:5000";
      }
    }
    // 3. Fallback to same origin
    return window.location.origin;
  },
  set API_BASE_URL(val) {
    if (val) {
      localStorage.setItem("API_BASE_URL", val.trim().replace(/\/+$/, ""));
    } else {
      localStorage.removeItem("API_BASE_URL");
    }
  },
  CURRENCY_SYMBOL: "₹",
  APP_TITLE: "Christmas Cake Challenge",
  CHURCH_NAME: "Church Youth Group, Pancode"
};

window.CONFIG = CONFIG;
