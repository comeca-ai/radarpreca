(function () {
  // Views do Balcão exigem login. A área Preca é pública e esconde a calculadora até haver sessão.
  var PROTECTED = { consulta: 1, bases: 1, lote: 1, regularizacao: 1 };
  var state = { user: null, ready: false };

  function root() { return document.documentElement; }

  function currentId() {
    return (location.hash || "").replace(/^#/, "").split("?")[0];
  }

  function tabFromHash() {
    var id = currentId();
    if (id === "login") return "login";
    if (typeof window.radarTabFromId === "function") return window.radarTabFromId(id);
    return "inicio";
  }

  function isProtected(tab) {
    return !!PROTECTED[tab];
  }

  function showAuthSlot() {
    var email = document.getElementById("auth-email");
    if (email) email.textContent = state.user ? state.user.email : "";
    var slot = document.querySelector(".auth-slot");
    if (slot) slot.hidden = !state.user;
  }

  function emitAuth() {
    window.dispatchEvent(new CustomEvent("radar-auth", { detail: { user: state.user } }));
  }

  window.radarWhenLoggedIn = function (fn) {
    var started = false;
    function go() {
      if (!state.user || started) return;
      started = true;
      fn();
    }
    window.addEventListener("radar-auth", go);
    if (state.ready) go();
  };

  function intendedFrom(tab, id) {
    if (isProtected(tab)) return id || tab;
    return "consulta";
  }

  window.radarGuardTab = function (tab, id) {
    if (tab === "login") return "login";
    if (!state.ready) return tab;
    if (state.user) return tab === "login" ? "consulta" : tab;
    if (isProtected(tab)) {
      try { sessionStorage.setItem("radar_next", intendedFrom(tab, id)); } catch (e) {}
      return "login";
    }
    return tab;
  };

  function applyTabs() {
    if (typeof window.radarApply === "function") window.radarApply(true);
  }

  async function refreshMe() {
    try {
      var r = await fetch("/api/me", { credentials: "same-origin" });
      if (r.ok) {
        state.user = await r.json();
        root().dataset.auth = "in";
      } else {
        state.user = null;
        root().dataset.auth = "out";
      }
    } catch (e) {
      state.user = null;
      root().dataset.auth = "out";
    }
    delete root().dataset.authPending;
    state.ready = true;
    showAuthSlot();
    emitAuth();

    var tab = tabFromHash();
    if (!state.user && isProtected(tab)) {
      try { sessionStorage.setItem("radar_next", intendedFrom(tab, currentId())); } catch (e) {}
      if (currentId() !== "login") {
        location.hash = "login";
        return;
      }
    }
    if (state.user && tab === "login") {
      var next = "consulta";
      try { next = sessionStorage.getItem("radar_next") || "consulta"; sessionStorage.removeItem("radar_next"); } catch (e) {}
      location.hash = next;
      return;
    }
    applyTabs();
  }

  function setErro(msg) {
    var el = document.getElementById("login-erro");
    if (!el) return;
    if (msg) {
      el.hidden = false;
      el.textContent = msg;
    } else {
      el.hidden = true;
      el.textContent = "";
    }
  }

  async function onLogin(e) {
    e.preventDefault();
    setErro("");
    var form = e.currentTarget;
    var email = (form.email.value || "").trim();
    var senha = form.senha.value || "";
    var btn = form.querySelector("button[type='submit']");
    if (btn) btn.disabled = true;
    try {
      var r = await fetch("/api/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ email: email, senha: senha })
      });
      var data = {};
      try { data = await r.json(); } catch (err) {}
      if (!r.ok) {
        setErro(data.detail || "E-mail ou senha incorretos.");
        return;
      }
      state.user = data;
      root().dataset.auth = "in";
      showAuthSlot();
      form.senha.value = "";
      var next = "consulta";
      try { next = sessionStorage.getItem("radar_next") || "consulta"; sessionStorage.removeItem("radar_next"); } catch (err) {}
      function arrive() {
        applyTabs();
        emitAuth();
      }
      var here = currentId();
      if (here === next || here.indexOf(next) === 0) {
        arrive();
      } else {
        var once = function () {
          window.removeEventListener("hashchange", once);
          arrive();
        };
        window.addEventListener("hashchange", once);
        location.hash = next;
      }
    } catch (err) {
      setErro("Não foi possível entrar. Tente de novo.");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function onSair(e) {
    e.preventDefault();
    try {
      await fetch("/api/logout", { method: "POST", credentials: "same-origin" });
    } catch (err) {}
    state.user = null;
    root().dataset.auth = "out";
    showAuthSlot();
    emitAuth();
    location.hash = "inicio";
    applyTabs();
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("form-login");
    if (form) form.addEventListener("submit", onLogin);
    var sair = document.getElementById("btn-sair");
    if (sair) sair.addEventListener("click", onSair);

    document.addEventListener("click", function (ev) {
      var a = ev.target && ev.target.closest ? ev.target.closest("a[data-next]") : null;
      if (!a || state.user) return;
      try { sessionStorage.setItem("radar_next", a.getAttribute("data-next")); } catch (err) {}
    });

    var tabs = document.querySelectorAll(".site-nav a[data-tab], .subnav a[href]");
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].addEventListener("click", function (ev) {
        if (state.user || !state.ready) return;
        var tab = ev.currentTarget.getAttribute("data-tab") || ev.currentTarget.getAttribute("data-sub") || "";
        if (!isProtected(tab)) return;
        ev.preventDefault();
        try { sessionStorage.setItem("radar_next", tab); } catch (err) {}
        location.hash = "login";
      });
    }
  });

  refreshMe();
})();
