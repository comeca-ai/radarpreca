(function () {
  var br = new Intl.NumberFormat("pt-BR");
  var brMoney = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  var brMoneyCompact = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function money(v) {
    if (v == null || v === "") return "—";
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return Math.abs(n) >= 1000000 ? brMoneyCompact.format(n) : brMoney.format(n);
  }
  function num(v) {
    if (v == null || v === "") return "—";
    return br.format(Number(v));
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function qs(params) {
    var u = new URLSearchParams();
    Object.keys(params).forEach(function (k) {
      var v = params[k];
      if (v !== undefined && v !== null && v !== "") u.set(k, v);
    });
    return u.toString();
  }

  var state = { page: 1 };

  function currentFilters() {
    var form = $("#form-consulta");
    var o = {};
    $all("input, select", form).forEach(function (el) {
      if (!el.name) return;
      var v = el.value && el.value.trim();
      if (v) o[el.name] = v;
    });
    var sortSel = $("#consulta-sort");
    if (sortSel) {
      if (sortSel.value === "valor_asc") { o.sort = "valor"; o.order = "asc"; }
      else if (sortSel.value === "posicao") { o.sort = "posicao"; o.order = "asc"; }
      else { o.sort = "valor"; o.order = "desc"; }
    }
    return o;
  }

  function statusLabel(s) {
    if (s === "pendente") return "Pendente";
    if (s === "pago") return "Pago";
    if (s === "expedido") return "Expedido";
    return s || "—";
  }
  function natLabel(s) {
    if (s === "alimentar") return "Alimentar";
    if (s === "comum") return "Comum";
    return "";
  }

  function renderCards(rows) {
    var el = $("#cards-consulta");
    if (!rows || !rows.length) {
      el.innerHTML = "<p class='empty-msg'>Nenhum precatório neste recorte. Tente outro número, ente ou fonte.</p>";
      return;
    }
    el.innerHTML = "<div class='consulta-cards'>" + rows.map(function (r) {
      var title = r.numero_precatorio || (r.chave ? "SIOP " + r.chave : "Sem número de precatório");
      var fila = "";
      if (r.status === "pendente" && r.ordem != null && r.ordem !== "") {
        var frente = r.creditos_a_frente != null
          ? " · " + num(r.creditos_a_frente) + " crédito" + (Number(r.creditos_a_frente) === 1 ? "" : "s") +
            " à frente (" + money(r.valor_a_frente) + ")"
          : "";
        var enteFila = r.ente_devedor ? " na fila de " + r.ente_devedor : " na fila";
        fila = "<p class='cc-fila'>Posição " + esc(r.ordem) + enteFila + frente + "</p>";
      }
      var nat = natLabel(r.natureza);
      return "<article class='consulta-card'>" +
        "<div class='cc-top'>" +
          "<span class='badge-status " + esc(r.status || "") + "'>" + esc(statusLabel(r.status)) + "</span>" +
          "<span class='chip-fonte'>" + esc(r.fonte_label || r.fonte) + "</span>" +
          (nat ? "<span class='chip-nat'>" + esc(nat) + "</span>" : "") +
        "</div>" +
        "<p class='cc-valor'>" + money(r.valor) + "</p>" +
        "<h3 class='cc-num'>" + esc(title) + "</h3>" +
        "<p class='cc-ente'>" + esc(r.ente_devedor || "Ente não informado nesta base") + "</p>" +
        "<div class='cc-meta'>" +
          "<span>Tribunal <strong>" + esc(r.tribunal || "—") + "</strong></span>" +
          "<span>Ano <strong>" + esc(r.ano_orcamento || "—") + "</strong></span>" +
          (r.cpf_cnpj_parcial ? "<span>CPF/CNPJ <strong>" + esc(r.cpf_cnpj_parcial) + "</strong></span>" : "") +
        "</div>" +
        fila +
        (r.status === "pendente" && r.fonte === "trf4_pendentes" && r.numero_precatorio
          ? "<p class='cc-actions'><a class='btn ghost btn-precificar' href='#precificacao?numero=" +
            encodeURIComponent(r.numero_precatorio) +
            "'>Precificar <span class='badge-v0'>v0</span></a></p>"
          : "") +
      "</article>";
    }).join("") + "</div>";
  }

  function renderPager(page, pages, total) {
    var el = $("#pager-consulta");
    if (pages <= 1) {
      el.innerHTML = total ? "<span class='pager-meta'>" + num(total) + " registros</span>" : "";
      return;
    }
    el.innerHTML =
      "<button type='button' class='pg' data-d='-1'" + (page <= 1 ? " disabled" : "") + ">Anterior</button>" +
      "<span class='pager-meta'>Página " + page + " de " + pages + " · " + num(total) + " registros</span>" +
      "<button type='button' class='pg' data-d='1'" + (page >= pages ? " disabled" : "") + ">Próxima</button>";
    $all(".pg", el).forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.page = page + Number(btn.getAttribute("data-d"));
        loadConsulta();
        var results = $("#consulta-resultados");
        if (results) results.scrollIntoView({ block: "start" });
      });
    });
  }

  function loadConsulta() {
    var meta = $("#meta-consulta");
    var params = currentFilters();
    params.page = state.page;
    params.page_size = 20;
    meta.textContent = "Buscando…";
    fetch("/api/consulta?" + qs(params)).then(function (r) { return r.json(); }).then(function (data) {
      var bits = [num(data.total) + " resultado" + (data.total === 1 ? "" : "s")];
      if (data.total) bits.push(money(data.soma_valor));
      if (data.ms != null) bits.push(data.ms + " ms");
      meta.textContent = bits.join(" · ");
      renderCards(data.rows);
      renderPager(data.page, data.pages, data.total);
    }).catch(function () {
      meta.textContent = "Não foi possível concluir a consulta.";
      $("#cards-consulta").innerHTML = "<p class='empty-msg'>Falha ao falar com a API. Tente de novo em instantes.</p>";
      $("#pager-consulta").innerHTML = "";
    });
  }

  function hashParams() {
    var hash = location.hash || "";
    var i = hash.indexOf("?");
    return new URLSearchParams(i >= 0 ? hash.slice(i + 1) : "");
  }

  function applyParamsToForm() {
    var form = $("#form-consulta");
    var hp = hashParams();
    var sp = new URLSearchParams(location.search);
    ["q", "fonte", "tribunal", "ente", "natureza", "status", "ano_orcamento", "min_valor", "max_valor"].forEach(function (k) {
      var v = hp.get(k) || sp.get(k);
      if (v == null) return;
      var el = form.querySelector("[name='" + k + "']");
      if (el) el.value = v;
    });
    var sort = hp.get("sort") || sp.get("sort");
    var order = hp.get("order") || sp.get("order");
    var sel = $("#consulta-sort");
    if (sel && sort === "posicao") sel.value = "posicao";
    else if (sel && sort === "valor" && order === "asc") sel.value = "valor_asc";
  }

  function isConsultaTab() {
    var hash = (location.hash || "").replace(/^#/, "").split("?")[0];
    var tab = document.documentElement.dataset.tab;
    if (tab && tab !== "consulta") return false;
    if (hash && hash !== "consulta") return false;
    return true;
  }

  function writeHash() {
    if (!isConsultaTab()) return;
    var o = currentFilters();
    var u = new URLSearchParams();
    Object.keys(o).forEach(function (k) {
      if (o[k]) u.set(k, o[k]);
    });
    var qs = u.toString();
    var next = "#consulta" + (qs ? "?" + qs : "");
    if (location.hash !== next) history.replaceState(null, "", next);
  }

  function init() {
    if (!$("#panel-consulta")) return;
    if (isConsultaTab()) applyParamsToForm();
    var filt = $(".consulta-filters");
    if (filt && window.matchMedia && window.matchMedia("(min-width: 800px)").matches) {
      filt.open = true;
    }
    var form = $("#form-consulta");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      state.page = 1;
      writeHash();
      loadConsulta();
    });
    form.addEventListener("reset", function () {
      setTimeout(function () { state.page = 1; loadConsulta(); }, 0);
    });
    var sortSel = $("#consulta-sort");
    if (sortSel) {
      sortSel.addEventListener("change", function () { state.page = 1; loadConsulta(); });
    }
    $all("#form-consulta select").forEach(function (el) {
      if (el.id === "consulta-sort") return;
      el.addEventListener("change", function () { state.page = 1; loadConsulta(); });
    });
    window.addEventListener("hashchange", function () {
      if (!isConsultaTab()) return;
      applyParamsToForm();
      writeHash();
      loadConsulta();
    });
    if (isConsultaTab()) {
      writeHash();
      loadConsulta();
    }
  }

  function boot() {
    if (typeof window.radarWhenLoggedIn === "function") {
      window.radarWhenLoggedIn(init);
      return;
    }
    window.addEventListener("radar-auth", function once(e) {
      if (e.detail && e.detail.user) {
        window.removeEventListener("radar-auth", once);
        init();
      }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
