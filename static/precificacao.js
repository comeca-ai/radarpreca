(function () {
  var br = new Intl.NumberFormat("pt-BR");
  var brMoney = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  var brPct = new Intl.NumberFormat("pt-BR", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
  var brPct2 = new Intl.NumberFormat("pt-BR", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var brNum = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
  var brT = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2, minimumFractionDigits: 0 });

  var REGRA = {
    otimista: { t_fator: 0.7, p_fator: 0.5, r_delta: -0.02 },
    base: { t_fator: 1, p_fator: 1, r_delta: 0 },
    pessimista: { t_fator: 1.5, p_fator: 1.5, r_delta: 0.03, p_teto: 0.95 }
  };

  var state = {
    prefill: null,
    tManual: false
  };

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function money(v) {
    if (v == null || v === "" || !isFinite(Number(v))) return "—";
    return brMoney.format(Number(v));
  }
  function pct(v) {
    if (v == null || !isFinite(Number(v))) return "—";
    return brPct.format(Number(v));
  }
  function pct2(v) {
    if (v == null || !isFinite(Number(v))) return "—";
    return brPct2.format(Number(v));
  }
  function num(v) {
    if (v == null || v === "" || !isFinite(Number(v))) return "—";
    return br.format(Number(v));
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function hashParams() {
    var hash = location.hash || "";
    var i = hash.indexOf("?");
    return new URLSearchParams(i >= 0 ? hash.slice(i + 1) : "");
  }
  function hashBase() {
    return (location.hash || "").replace(/^#/, "").split("?")[0];
  }
  function readNum(id) {
    var el = $(id);
    if (!el) return null;
    var raw = String(el.value || "").trim().replace(/\s/g, "").replace(",", ".");
    if (raw === "") return null;
    var n = Number(raw);
    return isFinite(n) ? n : null;
  }

  function calcular(valor, t, p, r, c, ir, hon) {
    if (valor == null || t == null || p == null || r == null) return null;
    if (valor < 0 || t < 0 || p < 0 || p > 1 || r <= -1 || c <= -1) return null;
    var descontos = (ir || 0) + (hon || 0);
    if (descontos >= 1 || (ir || 0) < 0 || (hon || 0) < 0) return null;
    var valorCorrigido = valor * Math.pow(1 + (c || 0), t);
    var valorPag = valorCorrigido * (1 - descontos);
    var fator = Math.pow(1 + r, t);
    var preco = fator === 0 ? 0 : valorPag * (1 - p) / fator;
    var desagio = valor === 0 ? null : 1 - preco / valor;
    return {
      valor: valor, t: t, p: p, r: r, c: c || 0, ir: ir || 0, hon: hon || 0,
      descontos: descontos, valorCorrigido: valorCorrigido, valorPag: valorPag,
      fator: fator, preco: preco, desagio: desagio, agio: desagio != null && desagio < 0
    };
  }

  function cenarioParams(t, p, r, nome) {
    var g = REGRA[nome];
    var t2 = Math.max(0, t * g.t_fator);
    var p2 = Math.min(g.p_teto != null ? g.p_teto : 1, Math.max(0, p * g.p_fator));
    var r2 = r + g.r_delta;
    if (r2 <= -0.999) r2 = -0.999;
    return { t: t2, p: p2, r: r2 };
  }

  function setVal(id, v) {
    var el = $(id);
    if (!el) return;
    if (v == null || v === "") el.value = "";
    else el.value = String(v);
  }

  function renderCredito(data) {
    var box = $("#precif-credito");
    var c = data && data.credito;
    if (!c) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }
    box.hidden = false;
    var frente = c.valor_a_frente != null
      ? num(c.creditos_a_frente) + " crédito" + (Number(c.creditos_a_frente) === 1 ? "" : "s") +
        " à frente (" + money(c.valor_a_frente) + ")"
      : "valor à frente não informado";
    box.innerHTML =
      "<h2>Crédito lido na fila pendente do TRF4</h2>" +
      "<p class='cc-valor'>" + money(c.valor) + "</p>" +
      "<p><strong>" + esc(c.numero_precatorio) + "</strong> · " + esc(c.ente_devedor || "Ente não informado") + "</p>" +
      "<div class='precif-meta'>" +
        "<span>Tribunal <strong>" + esc(c.tribunal || "—") + "</strong></span>" +
        "<span>Natureza <strong>" + esc(c.natureza || "—") + "</strong></span>" +
        "<span>Posição <strong>" + esc(c.ordem != null ? c.ordem : "—") + "</strong></span>" +
        "<span>Lista <strong>" + esc(c.tipo_lista || "—") + "</strong></span>" +
        (c.regime ? "<span>Regime <strong>" + esc(c.regime) + "</strong></span>" : "") +
        "<span>" + esc(frente) + "</span>" +
      "</div>";
  }

  function renderAvisos(data) {
    var box = $("#precif-avisos");
    var bits = [];
    if (data && data.pagamento_anual_fonte) {
      bits.push("<p><strong>Fonte do pagamento anual.</strong> " + esc(data.pagamento_anual_fonte.label) +
        (data.pagamento_anual_fonte.regime_mapa ? " Regime no mapa: " + esc(data.pagamento_anual_fonte.regime_mapa) + "." : "") +
        (data.pagamento_anual_fonte.saldo_devedor != null ? " Saldo devedor no mapa: " + money(data.pagamento_anual_fonte.saldo_devedor) + "." : "") +
        "</p>");
    }
    if (data && data.pagamento_anual_aviso) {
      bits.push("<p>" + esc(data.pagamento_anual_aviso) + "</p>");
    }
    if (data && data.t_observacao) {
      bits.push("<p>" + esc(data.t_observacao) + "</p>");
    }
    if (data && data.listas_pagos_nao_usadas) {
      bits.push("<p class='muted'>" + esc(data.listas_pagos_nao_usadas) + "</p>");
    }
    if (data && data.mapa_contexto && data.mapa_contexto.length) {
      var rows = data.mapa_contexto.map(function (r) {
        return "<tr><td>" + esc(r.nome_entidade) + "</td><td class='num'>" + money(r.pago_no_ano) +
          "</td><td>" + esc(r.tribunal) + " " + esc(r.ano) + "</td></tr>";
      }).join("");
      bits.push(
        "<div class='precif-contexto'><p><strong>Contexto do mapa, não usado no T.</strong> " +
        "Pagamento no ano dos entes federais listados à parte no mapa da dívida.</p>" +
        "<table><thead><tr><th>Ente no mapa</th><th>pago_no_ano</th><th>Fonte</th></tr></thead><tbody>" +
        rows + "</tbody></table></div>"
      );
    }
    box.innerHTML = bits.join("");
    box.hidden = bits.length === 0;
  }

  function applyPrefill(data) {
    state.prefill = data;
    state.tManual = false;
    var c = data && data.credito;
    if (c) {
      setVal("#precif-valor", c.valor);
      setVal("#precif-frente", c.valor_a_frente);
    }
    if (data && data.pagamento_anual != null) setVal("#precif-pagamento", data.pagamento_anual);
    else if (!c) { /* keep whatever the user typed on a blank load */ }
    else setVal("#precif-pagamento", "");

    var hip = (data && data.hipoteses_padrao) || {};
    if ($("#precif-correcao") && $("#precif-correcao").value === "") {
      setVal("#precif-correcao", ((hip.correcao_aa || 0) * 100));
    }
    if ($("#precif-r") && $("#precif-r").value === "") {
      setVal("#precif-r", ((hip.r_aa != null ? hip.r_aa : 0.10) * 100));
    }
    if ($("#precif-p") && $("#precif-p").value === "") {
      setVal("#precif-p", ((hip.p_padrao != null ? hip.p_padrao : 0.15) * 100));
    }
    if (c || data) {
      // Always reset hypothesis fields when loading a credit, so the example is reproducible
      setVal("#precif-correcao", ((hip.correcao_aa || 0) * 100));
      setVal("#precif-r", ((hip.r_aa != null ? hip.r_aa : 0.10) * 100));
      setVal("#precif-p", ((hip.p_padrao != null ? hip.p_padrao : 0.15) * 100));
      setVal("#precif-ir", 0);
      setVal("#precif-honorarios", 0);
    }
    var tLock = $("#precif-t-manual");
    if (tLock) tLock.checked = false;
    if (data && data.t_calculado != null) setVal("#precif-t", Number(data.t_calculado).toFixed(4));
    else setVal("#precif-t", "");
    markPreset();
    renderCredito(data);
    renderAvisos(data);
    recalcTFromPagamento();
    renderAll();
  }

  function recalcTFromPagamento() {
    if (state.tManual) return;
    var frente = readNum("#precif-frente");
    var pag = readNum("#precif-pagamento");
    if (frente == null || pag == null || pag <= 0) return;
    setVal("#precif-t", (frente / pag).toFixed(4));
  }

  function markPreset() {
    var p = readNum("#precif-p");
    $all(".precif-presets button").forEach(function (btn) {
      var v = Number(btn.getAttribute("data-p"));
      btn.setAttribute("aria-pressed", (p != null && Math.abs(p - v) < 0.001) ? "true" : "false");
    });
  }

  function inputs() {
    return {
      valor: readNum("#precif-valor"),
      frente: readNum("#precif-frente"),
      pagamento: readNum("#precif-pagamento"),
      t: readNum("#precif-t"),
      correcao: (readNum("#precif-correcao") || 0) / 100,
      ir: (readNum("#precif-ir") || 0) / 100,
      honorarios: (readNum("#precif-honorarios") || 0) / 100,
      p: (readNum("#precif-p") || 0) / 100,
      r: (readNum("#precif-r") || 0) / 100
    };
  }

  function renderAll() {
    var err = $("#precif-erro");
    var ins = inputs();
    markPreset();
    if (ins.valor == null || ins.t == null || ins.p == null || ins.r == null) {
      $("#precif-resultados").hidden = true;
      err.hidden = false;
      err.textContent = "Preencha o valor atual, o T, o p e o r para ver os cenários. Tudo isso é hipótese desta v0, não um laudo.";
      return;
    }
    if (ins.t < 0 || ins.valor < 0) {
      $("#precif-resultados").hidden = true;
      err.hidden = false;
      err.textContent = "Valor e T não podem ser negativos.";
      return;
    }
    if (ins.p < 0 || ins.p > 1) {
      $("#precif-resultados").hidden = true;
      err.hidden = false;
      err.textContent = "p precisa estar entre 0% e 100%.";
      return;
    }
    if (ins.ir + ins.honorarios >= 1) {
      $("#precif-resultados").hidden = true;
      err.hidden = false;
      err.textContent = "IR + honorários não podem somar 100% ou mais.";
      return;
    }
    err.hidden = true;
    $("#precif-resultados").hidden = false;

    var nomes = ["otimista", "base", "pessimista"];
    var labels = { otimista: "Otimista", base: "Base", pessimista: "Pessimista" };
    var calcs = {};
    nomes.forEach(function (n) {
      var par = n === "base" ? { t: ins.t, p: ins.p, r: ins.r } : cenarioParams(ins.t, ins.p, ins.r, n);
      calcs[n] = Object.assign({ nome: n }, par, calcular(ins.valor, par.t, par.p, par.r, ins.correcao, ins.ir, ins.honorarios) || {});
    });
    var desagios = nomes.map(function (n) { return calcs[n].desagio; }).filter(function (d) { return d != null; });
    var faixa = desagios.length ? { min: Math.min.apply(null, desagios), max: Math.max.apply(null, desagios) } : null;

    var faixaEl = $("#precif-faixa");
    if (faixa) {
      faixaEl.innerHTML =
        "<p class='tag-v0'>Faixa de deságio · v0 · hipótese</p>" +
        "<p class='faixa-num'>" + pct2(faixa.min) + " a " + pct2(faixa.max) + "</p>" +
        "<p>Deságio do cenário-base: <strong>" + pct2(calcs.base.desagio) + "</strong>" +
        (calcs.base.agio ? " (ágio: o preço sai acima do valor atual, porque a correção ou o prazo empurram o valor no pagamento)." : ".") +
        " Calculado como 1 − Preço / Valor atual hoje. Não é deságio de mercado.</p>";
    } else {
      faixaEl.innerHTML = "";
    }

    var cards = $("#precif-cenarios");
    cards.innerHTML = nomes.map(function (n) {
      var x = calcs[n];
      return "<article class='precif-cenario " + n + "'>" +
        "<span class='tag-v0'>" + labels[n] + " · v0</span>" +
        "<h3>Preço " + money(x.preco) + "</h3>" +
        "<p class='desagio'>" + (x.agio ? "Ágio " : "Deságio ") + pct2(x.desagio) + "</p>" +
        "<dl>" +
          "<dt>T usado</dt><dd>" + brT.format(x.t) + " anos</dd>" +
          "<dt>p usado</dt><dd>" + pct(x.p) + "</dd>" +
          "<dt>r usado</dt><dd>" + pct(x.r) + "</dd>" +
          "<dt>Valor no pagamento</dt><dd>" + money(x.valorPag) + "</dd>" +
        "</dl></article>";
    }).join("");

    var b = calcs.base;
    var brk = $("#precif-breakdown");
    var origem = state.prefill && state.prefill.t_origem;
    var tOrigem = state.tManual
      ? "T informado manualmente (sobreposição ao valor sugerido)."
      : (origem === "orcamento_federal" && state.prefill && state.prefill.t_atrasado
        ? "Hipótese: prazo constitucional do exercício já venceu; T mínimo de 0,25 ano (atrasado/prazo vencido), editável."
        : origem === "orcamento_federal"
        ? "Hipótese: T até 31/dez do ano orçamentário/proposta (CF art. 100, § 5º), editável."
        : (state.prefill && state.prefill.t_calculado != null
          ? "T = valor à frente / pago_no_ano do mapa, editável."
          : "T informado ou recalculado a partir do pagamento anual preenchido."));
    brk.innerHTML =
      "<h2>Fórmula e decomposição (cenário-base)</h2>" +
      "<p class='eq'>Valor no pagamento = Valor atual hoje × (1 + c)<sup>T</sup> × (1 − IR − honorários)</p>" +
      "<p class='eq'>Preço = Valor no pagamento × (1 − p) / (1 + r)<sup>T</sup></p>" +
      "<p class='eq'>Deságio = 1 − Preço / Valor atual hoje</p>" +
      "<table class='precif-breakdown'><tbody>" +
        row("Valor atual hoje", money(b.valor), "Valor do crédito (fila TRF4 ou informado).") +
        row("Taxa de correção c", pct(b.c), "Hipótese do usuário. Não é a Selic oficial desta tela.") +
        row("T (anos)", brT.format(b.t), tOrigem) +
        row("Valor corrigido até o pagamento", money(b.valorCorrigido), "Valor atual × (1 + c)^T") +
        row("IR + honorários", pct(b.descontos), "Hipótese. Descontos percentuais sobre o valor corrigido.") +
        row("Valor no pagamento", money(b.valorPag), "Valor corrigido × (1 − IR − honorários)") +
        row("p (não pagamento / atraso)", pct(b.p), "Hipótese. Presets desta v0 não são score do ente.") +
        row("r (retorno exigido a.a.)", pct(b.r), "Hipótese do usuário. Não é taxa de mercado medida.") +
        row("(1 + r)^T", brNum.format(b.fator), "Fator de desconto do fluxo.") +
        row("Preço", money(b.preco), "Valor no pagamento × (1 − p) / (1 + r)^T") +
        row("Deságio vs. valor atual", pct2(b.desagio), "1 − Preço / Valor atual hoje") +
      "</tbody></table>" +
      "<p class='muted' style='margin-top:10px'>Otimista e pessimista deslocam T, p e r por fatores fixos desta v0 " +
      "(T × 0,7 e p × 0,5 e r − 2 p.p.; T × 1,5 e p × 1,5 com teto de 95% e r + 3 p.p.). Não são um modelo estatístico.</p>";
  }

  function row(k, v, hint) {
    return "<tr><th>" + esc(k) + (hint ? "<div class='muted'>" + esc(hint) + "</div>" : "") +
      "</th><td class='num'>" + v + "</td></tr>";
  }

  function loadNumero(numero) {
    var meta = $("#precif-status");
    meta.textContent = "Carregando o crédito na fila do TRF4…";
    var q = numero ? ("?numero=" + encodeURIComponent(numero)) : "";
    return fetch("/api/precificar" + q).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (res) {
        if (!res.data) throw new Error("sem dados");
        if (!res.ok && !res.data.credito) {
          meta.textContent = res.data.erro || "Número não localizado na fila pendente do TRF4.";
          applyPrefill(res.data);
          return;
        }
        var c = res.data.credito;
        meta.textContent = c
          ? ("Crédito " + c.numero_precatorio + " lido da fila pendente do TRF4.")
          : "Calculadora em branco. Preencha os campos à mão.";
        applyPrefill(res.data);
      })
      .catch(function () {
        meta.textContent = "Não foi possível falar com a API de precificação.";
      });
  }

  function writeHash(numero) {
    var next = "#precificacao" + (numero ? "?numero=" + encodeURIComponent(numero) : "");
    if (location.hash !== next) history.replaceState(null, "", next);
  }

  function onHash() {
    if (hashBase() !== "precificacao") return;
    var numero = hashParams().get("numero");
    var form = $("#form-precif-busca");
    if (form && numero) {
      var inp = form.querySelector("[name='numero']");
      if (inp) inp.value = numero;
    }
    if (numero) loadNumero(numero);
    else if (!state.prefill) loadNumero("");
  }

  function init() {
    if (!$("#panel-precificacao")) return;

    var form = $("#form-precif-busca");
    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var numero = (form.querySelector("[name='numero']").value || "").trim();
        writeHash(numero);
        loadNumero(numero);
      });
    }

    $all(".precif-presets button").forEach(function (btn) {
      btn.addEventListener("click", function () {
        setVal("#precif-p", btn.getAttribute("data-p"));
        markPreset();
        renderAll();
      });
    });

    var tLock = $("#precif-t-manual");
    if (tLock) {
      tLock.addEventListener("change", function () {
        state.tManual = tLock.checked;
        if (!state.tManual) recalcTFromPagamento();
        renderAll();
      });
    }

    ["#precif-valor", "#precif-frente", "#precif-pagamento", "#precif-t",
     "#precif-correcao", "#precif-ir", "#precif-honorarios", "#precif-p", "#precif-r"].forEach(function (id) {
      var el = $(id);
      if (!el) return;
      el.addEventListener("input", function () {
        if (id === "#precif-t") {
          state.tManual = true;
          if (tLock) tLock.checked = true;
        }
        if (id === "#precif-frente" || id === "#precif-pagamento") {
          recalcTFromPagamento();
        }
        renderAll();
      });
    });

    window.addEventListener("hashchange", onHash);
    onHash();
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
