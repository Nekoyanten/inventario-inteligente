/* Pedido rápido de una mesa: un toque agrega, sin recargar la página; el cobro sale en una hoja con los billetes. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const raiz = $("#comanda");
  if (!raiz) return;
  const carta = JSON.parse($("#datos-carta").textContent);
  let estado = JSON.parse($("#datos-estado").textContent);
  const csrf = () => (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || $("[name=csrfmiddlewaretoken]").value;
  const pesos = (v) => "$" + Math.round(v).toLocaleString("es-CO");
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const sinTildes = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  let categoria = "*pop", busqueda = "";

  // ---------------------------------------------------------------- la carta
  const pintarCarta = () => {
    let lista = carta;
    if (busqueda) lista = carta.filter((p) => sinTildes(p.n).includes(busqueda));
    else if (categoria === "*pop") {
      lista = carta.filter((p) => p.pop < 999).sort((a, b) => a.pop - b.pop);
      if (!lista.length) lista = carta.slice(0, 24);
    } else if (categoria !== "*todo") lista = carta.filter((p) => p.c === categoria);
    $("#carta").innerHTML = lista.map((p) => {
      const n = estado.por_producto[p.id] || 0;
      return `<div class="plato${n ? " con" : ""}" data-id="${p.id}">
        <button type="button" class="plato-mas" aria-label="Agregar ${esc(p.n)}"><span class="plato-nombre">${esc(p.n)}</span><span class="plato-precio">${pesos(p.p)}</span></button>
        ${n ? `<span class="plato-cuenta" aria-label="${n} en el pedido">${n}</span><button type="button" class="plato-menos" aria-label="Quitar uno de ${esc(p.n)}">−</button>` : ""}</div>`;
    }).join("");
    $("#carta-vacia").hidden = lista.length > 0;
  };

  const pintarEstado = () => {
    $("#b-unidades").textContent = estado.unidades;
    $("#b-total").textContent = pesos(estado.a_pagar);
    $("#c-total").textContent = pesos(estado.a_pagar);
    $("#abrir-cobro").disabled = estado.unidades <= 0;
    $("#lista-pedido").innerHTML = estado.lineas.map((l) =>
      `<li><span class="ped-nombre"><b>${l.cantidad} ×</b> ${esc(l.nombre)}${l.promocion ? `<br><small class="suave">${esc(l.promocion)}</small>` : ""}</span>
        <span class="ped-valor">${pesos(l.valor)}</span><button type="button" class="plato-menos fijo" data-id="${l.producto}" aria-label="Quitar uno">−</button></li>`).join("")
      || '<li class="suave">Toca un producto para agregarlo.</li>';
    $("#parcial").innerHTML = estado.lineas.map((l) =>
      `<label class="en-linea"><input type="checkbox" name="items" value="${l.item}"> ${l.cantidad} × ${esc(l.nombre)} · ${pesos(l.valor)}</label>`).join("");
    pintarBilletes();
    pintarCarta();
  };

  let enCola = Promise.resolve();
  const enviar = (url, producto) => {
    // Respuesta inmediata en pantalla; el servidor confirma en orden
    const delta = url === raiz.dataset.pedir ? 1 : -1;
    estado.por_producto[producto] = Math.max(0, (estado.por_producto[producto] || 0) + delta);
    estado.unidades = Math.max(0, estado.unidades + delta);
    pintarCarta();
    $("#b-unidades").textContent = estado.unidades;
    enCola = enCola.then(async () => {
      const datos = new FormData();
      datos.append("producto", producto); datos.append("cantidad", "1");
      try {
        const r = await fetch(url, { method: "POST", body: datos, headers: { "X-CSRFToken": csrf(), "X-Requested-With": "fetch" } });
        const j = await r.json();
        if (j.error) aviso(j.error);
        if (j.total !== undefined) estado = j;
        else if (!r.ok) location.reload();
      } catch (e) { aviso("Sin conexión: revisa el pedido antes de cobrar."); }
      pintarEstado();
    });
  };

  const aviso = (texto) => {
    let a = $("#aviso-comanda");
    if (!a) { a = document.createElement("p"); a.id = "aviso-comanda"; a.className = "mensaje error"; a.setAttribute("role", "alert"); raiz.prepend(a); }
    a.textContent = texto;
    setTimeout(() => a.remove(), 5000);
  };

  $("#carta").addEventListener("click", (e) => {
    const plato = e.target.closest(".plato");
    if (!plato) return;
    enviar(e.target.closest(".plato-menos") ? raiz.dataset.menos : raiz.dataset.pedir, Number(plato.dataset.id));
    if (navigator.vibrate) navigator.vibrate(8);
  });
  $("#lista-pedido").addEventListener("click", (e) => {
    const b = e.target.closest(".plato-menos");
    if (b) enviar(raiz.dataset.menos, Number(b.dataset.id));
  });
  document.querySelectorAll(".cat").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".cat").forEach((x) => x.classList.remove("activa"));
    b.classList.add("activa"); categoria = b.dataset.cat; busqueda = ""; $("#carta-buscar").value = ""; pintarCarta();
  }));
  $("#carta-buscar").addEventListener("input", (e) => { busqueda = sinTildes(e.target.value.trim()); pintarCarta(); });

  // ---------------------------------------------------------------- hojas
  const abrir = (id) => { const d = $(id); d.showModal ? d.showModal() : d.setAttribute("open", ""); };
  document.querySelectorAll(".hoja .cerrar").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));
  document.querySelectorAll(".hoja").forEach((d) => d.addEventListener("click", (e) => { if (e.target === d) d.close(); }));
  $("#ver-pedido").addEventListener("click", () => abrir("#hoja-pedido"));
  $("#abrir-cobro").addEventListener("click", () => enCola.then(() => { pintarEstado(); abrir("#hoja-cobro"); }));

  // ---------------------------------------------------------------- cobro
  const paga = $("#paga_con"), propina = $("#propina"), vueltas = $("#vueltas");
  const totalCobro = () => estado.a_pagar + Number(propina?.value || 0);
  function pintarBilletes() {
    const t = totalCobro();
    const opciones = [...new Set([t, ...[10000, 20000, 50000, 100000, 200000].filter((b) => b > t)])].slice(0, 5);
    $("#billetes").innerHTML = opciones.map((v, i) => `<button type="button" class="billete" data-v="${v}">${i === 0 ? "Exacto" : pesos(v)}</button>`).join("");
    calcular();
  }
  const calcular = () => {
    const efectivo = $("input[name=medio_pago]:checked").value === "EFECTIVO";
    $("#zona-efectivo").hidden = !efectivo;
    const t = totalCobro(), recibido = Number(paga.value || 0);
    document.querySelectorAll(".billete").forEach((b) => b.classList.toggle("elegido", Number(b.dataset.v) === recibido));
    vueltas.textContent = !efectivo || !recibido ? "" : recibido < t ? "Faltan " + pesos(t - recibido) : recibido === t ? "Pago exacto" : "Vueltas " + pesos(recibido - t);
    vueltas.classList.toggle("falta", recibido > 0 && recibido < t);
    $("#confirmar-cobro").textContent = "Cobrar " + pesos(t) + " y dejar la mesa libre";
  };
  $("#billetes").addEventListener("click", (e) => { const b = e.target.closest(".billete"); if (b) { paga.value = b.dataset.v; calcular(); } });
  [paga, propina].forEach((el) => el && el.addEventListener("input", () => (el === propina ? pintarBilletes() : calcular())));
  document.querySelectorAll("input[name=medio_pago]").forEach((r) => r.addEventListener("change", calcular));
  $("#form-cobrar").addEventListener("submit", (e) => {
    const b = e.submitter;
    if (b && b.id === "confirmar-cobro") { b.disabled = true; b.textContent = "Cobrando…"; }
  });

  pintarEstado();
})();
