/**
 * Authentication and Session Management
 */
const Auth = {
  getToken() {
    return localStorage.getItem("auth_token");
  },

  getUser() {
    const raw = localStorage.getItem("auth_user");
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  },

  isLoggedIn() {
    return !!this.getToken() && !!this.getUser();
  },

  isAdmin() {
    const user = this.getUser();
    return user && user.role === "admin";
  },

  isMember() {
    const user = this.getUser();
    return user && user.role === "member";
  },

  async loginAdmin(email, password) {
    const res = await API.post("/api/auth/admin-login", { email, password });
    if (res.success && res.data) {
      localStorage.setItem("auth_token", res.data.token);
      localStorage.setItem("auth_user", JSON.stringify(res.data.user));
    }
    return res;
  },

  async loginMember(name, code) {
    const res = await API.post("/api/auth/member-login", { name, code });
    if (res.success && res.data) {
      localStorage.setItem("auth_token", res.data.token);
      localStorage.setItem("auth_user", JSON.stringify(res.data.user));
    }
    return res;
  },

  async logout() {
    try {
      await API.post("/api/auth/logout", {});
    } catch (e) {
      // Continue client cleanup even if API fails
    }
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_user");
    const isInsideAdmin = window.location.pathname.includes("/admin/");
    window.location.href = isInsideAdmin ? "../login.html" : "login.html";
  },

  requireRole(requiredRole) {
    if (!this.isLoggedIn()) {
      const isInsideAdmin = window.location.pathname.includes("/admin/");
      window.location.href = isInsideAdmin ? "../login.html" : "login.html";
      return false;
    }

    const user = this.getUser();
    if (requiredRole === "admin" && user.role !== "admin") {
      alert("Access restricted to administrators.");
      window.location.href = window.location.pathname.includes("/admin/") ? "../dashboard.html" : "dashboard.html";
      return false;
    }

    if (requiredRole === "member" && user.role !== "member") {
      if (user.role === "admin") {
        // Admin can view member pages or redirect to admin
        return true;
      }
      window.location.href = "login.html";
      return false;
    }

    return true;
  }
};

window.Auth = Auth;
