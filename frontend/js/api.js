/**
 * Centralized API Client with JWT Bearer Token Injection & Error Handling
 */
const API = {
  async request(endpoint, options = {}) {
    const url = `${CONFIG.API_BASE_URL}${endpoint}`;
    const token = localStorage.getItem("auth_token");

    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {})
    };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers
      });

      // Handle 401 Unauthorized (session expired)
      if (response.status === 401) {
        if (!window.location.pathname.endsWith("login.html") && !window.location.pathname.endsWith("index.html")) {
          localStorage.removeItem("auth_token");
          localStorage.removeItem("auth_user");
          window.location.href = window.location.pathname.includes("/admin/") ? "../login.html?expired=1" : "login.html?expired=1";
          return { success: false, error: "Session expired. Please log in again." };
        }
      }

      // Check if response is JSON
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        const data = await response.json();
        if (!response.ok && !data.error) {
          data.error = `Server error (${response.status})`;
        }
        return data;
      } else {
        if (!response.ok) {
          const text = await response.text();
          return { success: false, error: text || `HTTP error ${response.status}` };
        }
        return { success: true, response };
      }
    } catch (err) {
      console.error(`API request failed: ${endpoint}`, err);
      return {
        success: false,
        error: "Unable to connect to the backend server. Please verify your connection or backend URL settings."
      };
    }
  },

  get(endpoint, params = {}) {
    const query = new URLSearchParams(params).toString();
    const url = query ? `${endpoint}?${query}` : endpoint;
    return this.request(url, { method: "GET" });
  },

  post(endpoint, data = {}) {
    return this.request(endpoint, {
      method: "POST",
      body: JSON.stringify(data)
    });
  },

  put(endpoint, data = {}) {
    return this.request(endpoint, {
      method: "PUT",
      body: JSON.stringify(data)
    });
  },

  delete(endpoint) {
    return this.request(endpoint, { method: "DELETE" });
  },

  getDownloadUrl(endpoint) {
    const token = localStorage.getItem("auth_token") || "";
    return `${CONFIG.API_BASE_URL}${endpoint}?token=${encodeURIComponent(token)}`;
  }
};

window.API = API;
