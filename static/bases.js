(function () {
  var br = new Intl.NumberFormat("pt-BR");
  var brMoney = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
  var brMoneyFull = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function money(v) {
    if (v == null || v === "") return "—";
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return Math.abs(n) >= 1000000 ? brMoney.format(n) : brMoneyFull.format(n);
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

  function fillSelect(el, values, firstLabel) {
    var cur = el.value;
    el.innerHTML = "";
    var opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = firstLabel || "Todos";
    el.appendChild(opt0);
    (values || []).forEach(function (v) {
      if (!v) return;
      var o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      el.appendChild(o);
    });
    if (cur) el.value = cur;
  }

  function renderTable(el, columns, rows) {
    if (!rows || !rows.length) {
      el.innerHTML = "<p class='empty-msg'>Nenhum registro neste filtro.</p>";
      return;
    }
    var thead = "<thead><tr>" + columns.map(function (c) {
      return "<th>" + esc(c.label) + "</th>";
    }).join("") + "</tr></thead>";
    var body = rows.map(function (row) {
      return "<tr>" + columns.map(function (c) {
        var v = row[c.key];
        var text = c.money ? money(v) : (v == null || v === "" ? "—" : esc(v));
        var cls = c.money ? " class='num'" : "";
        return "<td" + cls + " data-label='" + esc(c.label) + "'>" + text + "</td>";
      }).join("") + "</tr>";
    }).join("");
    el.innerHTML = "<div class='table-scroll'><table class='data'>" + thead + "<tbody>" + body + "</tbody></table></div>";
  }

  function pager(el, page, pages, total, onPage) {
    if (pages <= 1) {
      el.innerHTML = "<span class='pager-meta'>" + num(total) + " registros</span>";
      return;
    }
    el.innerHTML =
      "<button type='button' class='pg' data-d='-1'" + (page <= 1 ? " disabled" : "") + ">Anterior</button>" +
      "<span class='pager-meta'>Página " + page + " de " + pages + " · " + num(total) + " registros</span>" +
      "<button type='button' class='pg' data-d='1'" + (page >= pages ? " disabled" : "") + ">Próxima</button>";
    $all(".pg", el).forEach(function (btn) {
      btn.addEventListener("click", function () {
        onPage(page + Number(btn.getAttribute("data-d")));
      });
    });
  }

  var state = { siop: 1, pendentes: 1, pagos: 1, mapas: 1, extra: 1 };

  function loadBases() {
    return fetch("/api/bases").then(function (r) { return r.json(); }).then(function (data) {
      var grid = $("#bases-cards");
      if (!grid) return;
      grid.innerHTML = (data.bases || []).map(function (b) {
        return "<article class='card base-card'>" +
          "<p class='tag'>" + esc(b.id) + "</p>" +
          "<h3>" + esc(b.nome) + "</h3>" +
          "<p><strong>" + num(b.registros) + "</strong> registros</p>" +
          "<p class='src'>Fonte: " + (b.url ? "<a href='" + esc(b.url) + "' target='_blank' rel='noopener'>" + esc(b.fonte) + "</a>" : esc(b.fonte)) + "</p>" +
          "<p class='src'>Arquivo de origem: " + esc(b.arquivo_origem) + "</p>" +
          "<p class='src'>Testado em " + esc(b.testado_em) + "</p>" +
          (b.limites ? "<p class='limite'>" + esc(b.limites) + "</p>" : "") +
          "</article>";
      }).join("");
    });
  }

  function loadStats() {
    return fetch("/api/stats").then(function (r) { return r.json(); }).then(function (data) {
      var s = data.stats || {};
      var box = $("#bases-kpis");
      if (box) {
        box.innerHTML = [
          ["Registros SIOP", num(s.n)],
          ["Valor atualizado", money(s.sum_atu)],
          ["Mediana", money(s.desc_atu && s.desc_atu["50%"])],
          ["1% concentra", ((s.top1_share || 0) * 100).toFixed(1).replace(".", ",") + "%"]
        ].map(function (item) {
          return "<div class='kpi'><p class='kpi-label'>" + item[0] + "</p><p class='kpi-value'>" + item[1] + "</p></div>";
        }).join("");
      }
      var figs = $("#bases-charts");
      if (figs) {
        figs.innerHTML = (data.graficos || []).map(function (g) {
          return "<figure class='chart'><img src='" + esc(g.arquivo) + "' alt='" + esc(g.titulo) + "'><figcaption>" + esc(g.titulo) + "</figcaption></figure>";
        }).join("");
      }
    });
  }

  function currentFilters(form) {
    var o = {};
    $all("input, select", form).forEach(function (el) {
      if (!el.name) return;
      var v = el.value && el.value.trim();
      if (v) o[el.name] = v;
    });
    return o;
  }

  function loadSiop() {
    var form = $("#form-siop");
    var params = currentFilters(form);
    params.page = state.siop;
    params.page_size = 25;
    var meta = $("#meta-siop");
    var table = $("#table-siop");
    var pg = $("#pager-siop");
    meta.textContent = "Carregando…";
    fetch("/api/siop?" + qs(params)).then(function (r) { return r.json(); }).then(function (data) {
      meta.textContent = num(data.total) + " precatórios · " + money(data.soma_valor_atualizado) + " atualizados";
      renderTable(table, [
        { key: "chave", label: "Chave" },
        { key: "nome_tribunal", label: "Tribunal" },
        { key: "nome_uo", label: "UO / ente" },
        { key: "tipo_causa", label: "Tipo de causa" },
        { key: "class_nfgc", label: "Classe" },
        { key: "data_autuacao", label: "Autuação" },
        { key: "valor_atualizado", label: "Valor atualizado", money: true }
      ], data.rows);
      pager(pg, data.page, data.pages, data.total, function (p) { state.siop = p; loadSiop(); });
      $("#dl-siop").href = "/api/download/siop.csv?" + qs(currentFilters(form));
    }).catch(function () { meta.textContent = "Não foi possível carregar a base SIOP."; });
  }

  function loadPendentes() {
    var form = $("#form-pendentes");
    var params = currentFilters(form);
    params.page = state.pendentes;
    params.page_size = 25;
    var meta = $("#meta-pendentes");
    meta.textContent = "Carregando…";
    fetch("/api/trf4/pendentes?" + qs(params)).then(function (r) { return r.json(); }).then(function (data) {
      meta.textContent = num(data.total) + " precatórios pendentes · " + money(data.soma_valor);
      renderTable($("#table-pendentes"), [
        { key: "ordem", label: "Ordem" },
        { key: "ente_devedor", label: "Ente devedor" },
        { key: "numero_precatorio", label: "Precatório" },
        { key: "ano_orcamento", label: "Proposta" },
        { key: "natureza", label: "Natureza" },
        { key: "tipo_lista", label: "Lista" },
        { key: "data_apresentacao", label: "Autuação" },
        { key: "valor", label: "Valor", money: true }
      ], data.rows);
      pager($("#pager-pendentes"), data.page, data.pages, data.total, function (p) { state.pendentes = p; loadPendentes(); });
      $("#dl-pendentes").href = "/api/download/trf4_pendentes.csv?" + qs(currentFilters(form));
    }).catch(function () { meta.textContent = "Não foi possível carregar a fila pendente do TRF4."; });
  }

  function loadPagos() {
    var form = $("#form-pagos");
    var params = currentFilters(form);
    params.page = state.pagos;
    params.page_size = 25;
    var meta = $("#meta-pagos");
    meta.textContent = "Carregando…";
    fetch("/api/trf/pagos?" + qs(params)).then(function (r) { return r.json(); }).then(function (data) {
      meta.textContent = num(data.total) + " pagamentos · " + money(data.soma_valor_pago);
      renderTable($("#table-pagos"), [
        { key: "tribunal", label: "Tribunal" },
        { key: "proposta", label: "Proposta" },
        { key: "ordem", label: "Ordem" },
        { key: "numero_precatorio", label: "Precatório" },
        { key: "cpf_cnpj_parcial", label: "CPF/CNPJ parcial" },
        { key: "base_legal", label: "Base legal" },
        { key: "data_pagamento", label: "Pagamento" },
        { key: "valor_pago", label: "Valor pago", money: true }
      ], data.rows);
      pager($("#pager-pagos"), data.page, data.pages, data.total, function (p) { state.pagos = p; loadPagos(); });
      $("#dl-pagos").href = "/api/download/trf_pagos.csv?" + qs(currentFilters(form));
    }).catch(function () { meta.textContent = "Não foi possível carregar os pagamentos."; });
  }

  function loadMapas() {
    var form = $("#form-mapas");
    var params = currentFilters(form);
    params.page = state.mapas;
    params.page_size = 25;
    var meta = $("#meta-mapas");
    meta.textContent = "Carregando…";
    fetch("/api/trf/mapas?" + qs(params)).then(function (r) { return r.json(); }).then(function (data) {
      meta.textContent = num(data.total) + " entes · pago no ano " + money(data.soma_pago_no_ano) + " · saldo " + money(data.soma_saldo_devedor);
      renderTable($("#table-mapas"), [
        { key: "tribunal", label: "Tribunal" },
        { key: "ano", label: "Ano" },
        { key: "nome_entidade", label: "Ente devedor" },
        { key: "cnpj", label: "CNPJ (fonte)" },
        { key: "uf", label: "UF" },
        { key: "esfera", label: "Esfera" },
        { key: "pago_no_ano", label: "Pago no ano", money: true },
        { key: "saldo_devedor", label: "Saldo devedor", money: true },
        { key: "expedidos_no_ano", label: "Expedidos no ano", money: true }
      ], data.rows);
      pager($("#pager-mapas"), data.page, data.pages, data.total, function (p) { state.mapas = p; loadMapas(); });
      $("#dl-mapas").href = "/api/download/trf_mapas.csv?" + qs(currentFilters(form));
    }).catch(function () { meta.textContent = "Não foi possível carregar os mapas."; });
  }

  function loadExtra() {
    var form = $("#form-extra");
    var params = currentFilters(form);
    params.page = state.extra;
    params.page_size = 25;
    var meta = $("#meta-extra");
    meta.textContent = "Carregando…";
    fetch("/api/trf/extra?" + qs(params)).then(function (r) { return r.json(); }).then(function (data) {
      meta.textContent = num(data.total) + " depósitos · " + money(data.soma_valor_depositado);
      renderTable($("#table-extra"), [
        { key: "entidade_devedora", label: "Ente devedor" },
        { key: "numero_precatorio", label: "Precatório" },
        { key: "proposta", label: "Proposta" },
        { key: "natureza", label: "Natureza" },
        { key: "parcela", label: "Parcela" },
        { key: "data_deposito", label: "Depósito" },
        { key: "valor_depositado", label: "Valor depositado", money: true }
      ], data.rows);
      pager($("#pager-extra"), data.page, data.pages, data.total, function (p) { state.extra = p; loadExtra(); });
    }).catch(function () { meta.textContent = "Não foi possível carregar os extraorçamentários."; });
  }

  function bindForm(id, loader, key) {
    var form = $(id);
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      state[key] = 1;
      loader();
    });
    form.addEventListener("reset", function () {
      setTimeout(function () { state[key] = 1; loader(); }, 0);
    });
  }

  function switchExplorer(name) {
    $all(".expl-tab").forEach(function (t) {
      t.setAttribute("aria-selected", t.getAttribute("data-expl") === name ? "true" : "false");
    });
    $all(".expl-panel").forEach(function (p) {
      p.hidden = p.id !== "expl-" + name;
    });
  }

  function init() {
    if (!$("#panel-bases")) return;
    loadBases();
    loadStats();
    fetch("/api/siop/facets").then(function (r) { return r.json(); }).then(function (f) {
      fillSelect($("#siop-tribunal"), f.tribunais, "Todos os tribunais");
      fillSelect($("#siop-nfgc"), f.nfgc, "Todas as classes");
      fillSelect($("#siop-uo"), f.uos, "Todas as UOs (principais)");
    }).finally(function () { loadSiop(); });
    loadPendentes();
    loadPagos();
    loadMapas();
    loadExtra();
    bindForm("#form-siop", loadSiop, "siop");
    bindForm("#form-pendentes", loadPendentes, "pendentes");
    bindForm("#form-pagos", loadPagos, "pagos");
    bindForm("#form-mapas", loadMapas, "mapas");
    bindForm("#form-extra", loadExtra, "extra");
    $all(".expl-tab").forEach(function (t) {
      t.addEventListener("click", function () { switchExplorer(t.getAttribute("data-expl")); });
    });
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
