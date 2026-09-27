/* Inventario Inteligente — JavaScript sin dependencias. */
const Inventario = (() => {
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const csrf = () => document.cookie.split("; ").find((c) => c.startsWith("csrftoken="))?.split("=")[1] || "";
  const pesos = (n) => "$" + Math.round(n).toLocaleString("es-CO");
  const cant = (n) => Number(n).toLocaleString("es-CO", { maximumFractionDigits: 3 });
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  function debounce(fn, ms = 250) {
    let t;
    return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  }

  async function buscarProductos(q) {
    const r = await fetch(`/productos/buscar.json?q=${encodeURIComponent(q)}`, { headers: { Accept: "application/json" } });
    return r.ok ? (await r.json()).resultados : [];
  }

  /* Autocompletado: <input data-buscador-producto data-destino="#id_producto"> */
  function buscadorProducto(input, alElegir) {
    const lista = document.createElement("div");
    lista.className = "resultados";
    input.after(lista);
    const pintar = (items) => {
      lista.innerHTML = items.map((p) => `<button type="button" class="producto-btn" data-id="${p.id}">
        <b>${esc(p.nombre)}</b><small class="suave">${esc(p.sku)} · stock ${cant(p.stock)} ${esc(p.unidad)}</small></button>`).join("");
      lista.querySelectorAll("button").forEach((b, i) => b.addEventListener("click", () => {
        alElegir(items[i]);
        lista.innerHTML = "";
      }));
    };
    input.addEventListener("input", debounce(async () => {
      if (input.value.trim().length < 2) { lista.innerHTML = ""; return; }
      pintar(await buscarProductos(input.value));
    }));
  }

  /* Formulario de producto: atributos por categoría + margen en vivo */
  function formularioProducto() {
    const cat = $("#id_categoria"), cont = $("#atributos");
    if (cat && cont) {
      cat.addEventListener("change", async () => {
        cont.innerHTML = "";
        if (!cat.value) return;
        const r = await fetch(`/productos/atributos/${cat.value}/`);
        if (!r.ok) return;
        const { atributos } = await r.json();
        cont.innerHTML = atributos.map((a) => {
          const nombre = `atributo__${a.id}`, req = a.obligatorio ? "required" : "";
          const campo = a.tipo === "OPCION" && a.opciones.length
            ? `<select name="${nombre}" id="id_${nombre}" ${req}><option value="">—</option>${a.opciones.map((o) => `<option>${esc(o)}</option>`).join("")}</select>`
            : `<input name="${nombre}" id="id_${nombre}" ${a.tipo === "NUMERO" ? 'type="number" step="any"' : ""} ${req}>`;
          return `<p><label for="id_${nombre}">${esc(a.nombre)}:</label>${campo}</p>`;
        }).join("");
      });
    }
    const compra = $("#id_precio_compra"), venta = $("#id_precio_venta"), margen = $("#margen");
    const actualizar = () => {
      if (!compra || !venta || !margen) return;
      const c = parseFloat(compra.value), v = parseFloat(venta.value);
      margen.textContent = c > 0 && v > 0 ? `Margen: ${(((v - c) / v) * 100).toFixed(0)} % · ganas ${pesos(v - c)} por unidad` : "";
    };
    [compra, venta].forEach((el) => el && el.addEventListener("input", actualizar));
    actualizar();
  }

  /* Formulario de movimiento: elegir producto con buscador */
  function formularioMovimiento() {
    const input = $("#buscar-producto"), oculto = $("#id_producto"), elegido = $("#producto-elegido");
    if (!input) return;
    buscadorProducto(input, (p) => {
      oculto.value = p.id;
      elegido.innerHTML = `<strong>${esc(p.nombre)}</strong> · stock actual ${cant(p.stock)} ${esc(p.unidad)}`;
      input.value = "";
    });
    const tipo = $("#id_tipo"), venc = $("#fila-vencimiento"), costo = $("#fila-costo");
    const mostrar = () => {
      const entrada = tipo && tipo.value.startsWith("ENTRADA_");
      if (venc) venc.hidden = !entrada;
      if (costo) costo.hidden = !entrada;
    };
    tipo && tipo.addEventListener("change", mostrar);
    mostrar();
  }

  /* Punto de venta */
  function pos({ urlRegistrar, urlTicket }) {
    const carrito = new Map();
    const q = $("#pos-buscar"), res = $("#pos-resultados"), cont = $("#pos-carrito"), totalEl = $("#pos-total"), btn = $("#pos-cobrar"), err = $("#pos-error");

    const pintarResultados = (items) => {
      res.innerHTML = items.map((p, i) => `<button type="button" class="producto-btn" data-i="${i}" ${p.stock <= 0 ? "disabled" : ""}>
        ${p.imagen ? `<img src="${esc(p.imagen)}" alt="" loading="lazy" class="miniatura-pos">` : ""}<b>${esc(p.nombre)}</b>${pesos(p.precio_venta)}<br><small class="suave">${p.stock <= 0 ? "Agotado" : "Stock " + cant(p.stock)}</small></button>`).join("");
      res.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => agregar(items[b.dataset.i])));
    };
    const agregar = (p) => {
      const linea = carrito.get(p.id) || { ...p, cantidad: 0 };
      if (linea.cantidad + 1 > p.stock) { avisar(`Solo hay ${cant(p.stock)} de ${p.nombre}.`); return; }
      linea.cantidad += 1;
      carrito.set(p.id, linea);
      pintarCarrito();
      q.value = ""; res.innerHTML = ""; q.focus();
    };
    const avisar = (m) => { err.textContent = m; err.hidden = !m; };
    const total = () => [...carrito.values()].reduce((s, l) => s + l.cantidad * l.precio_venta, 0);
    const pintarCarrito = () => {
      avisar("");
      cont.innerHTML = carrito.size ? [...carrito.values()].map((l) => `<div class="carrito-linea">
          <div><b>${esc(l.nombre)}</b><br><small class="suave">${pesos(l.precio_venta)} c/u</small></div>
          <input type="number" min="0" step="${l.decimales ? "0.001" : "1"}" value="${l.cantidad}" data-id="${l.id}" aria-label="Cantidad de ${esc(l.nombre)}">
          <b>${pesos(l.cantidad * l.precio_venta)}</b></div>`).join("")
        : '<p class="vacio">Agrega productos buscándolos o escaneando su código.</p>';
      cont.querySelectorAll("input").forEach((inp) => inp.addEventListener("change", () => {
        const l = carrito.get(Number(inp.dataset.id));
        const v = parseFloat(inp.value) || 0;
        if (v > l.stock) { inp.value = l.cantidad; avisar(`Solo hay ${cant(l.stock)} de ${l.nombre}.`); return; }
        if (v <= 0) carrito.delete(l.id); else l.cantidad = v;
        pintarCarrito();
      }));
      totalEl.textContent = pesos(total());
      btn.disabled = carrito.size === 0;
      const recibido = $("#pos-recibido"), cambio = $("#pos-cambio");
      if (recibido && cambio) {
        const r = parseFloat(recibido.value) || 0;
        cambio.textContent = r >= total() && total() > 0 ? `Cambio: ${pesos(r - total())}` : "";
      }
    };

    q.addEventListener("input", debounce(async () => {
      const texto = q.value.trim();
      if (!texto) { res.innerHTML = ""; return; }
      const items = await buscarProductos(texto);
      // Lectores de código de barras: coincidencia exacta → agregar directo
      const exacto = items.find((p) => p.codigo_barras && p.codigo_barras === texto);
      if (exacto) { agregar(exacto); res.innerHTML = ""; return; }
      pintarResultados(items);
    }, 200));
    $("#pos-recibido")?.addEventListener("input", pintarCarrito);

    btn.addEventListener("click", async () => {
      btn.disabled = true;
      const cuerpo = {
        lineas: [...carrito.values()].map((l) => ({ producto: l.id, cantidad: l.cantidad })),
        medio_pago: $("#pos-medio").value,
        cliente: $("#pos-cliente").value,
      };
      const r = await fetch(urlRegistrar, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(cuerpo) });
      const datos = await r.json().catch(() => ({}));
      if (r.ok) { window.location = urlTicket.replace("0", datos.venta); return; }
      avisar(datos.error || "No se pudo registrar la venta.");
      btn.disabled = false;
    });

    // Escáner con la cámara (BarcodeDetector, disponible en Chrome/Android)
    const escanear = $("#pos-escanear");
    if (escanear && "BarcodeDetector" in window) {
      escanear.hidden = false;
      escanear.addEventListener("click", () => escanearCodigo((codigo) => { q.value = codigo; q.dispatchEvent(new Event("input")); }));
    }
    pintarCarrito();
    q.focus();
  }

  async function escanearCodigo(alLeer) {
    const video = document.createElement("video");
    const capa = document.createElement("div");
    capa.style.cssText = "position:fixed;inset:0;background:#000c;z-index:50;display:grid;place-items:center";
    video.style.cssText = "max-width:92vw;max-height:70vh;border-radius:12px";
    const cerrar = document.createElement("button");
    cerrar.textContent = "Cerrar"; cerrar.className = "boton boton-auto";
    capa.append(video, cerrar); document.body.append(capa);
    let stream;
    const fin = () => { stream?.getTracks().forEach((t) => t.stop()); capa.remove(); };
    cerrar.onclick = fin;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      video.srcObject = stream; await video.play();
      const detector = new BarcodeDetector();
      const ciclo = async () => {
        if (!capa.isConnected) return;
        const codigos = await detector.detect(video).catch(() => []);
        if (codigos.length) { fin(); alLeer(codigos[0].rawValue); return; }
        requestAnimationFrame(ciclo);
      };
      ciclo();
    } catch { fin(); alert("No se pudo abrir la cámara."); }
  }

  /* Editor de líneas (órdenes de compra, facturas): buscar producto → fila con cantidad y costo */
  function editorLineas({ conVencimiento = false } = {}) {
    const cuerpo = $("#lineas"), total = $("#lineas-total"), input = $("#lineas-buscar");
    const recalcular = () => {
      let t = 0;
      cuerpo.querySelectorAll("tr").forEach((tr) => {
        const c = parseFloat(tr.querySelector("[name=lineas-cantidad]").value) || 0;
        const k = parseFloat(tr.querySelector("[name=lineas-costo]").value) || 0;
        tr.querySelector(".subtotal").textContent = pesos(c * k);
        t += c * k;
      });
      total.textContent = pesos(t);
      $("#lineas-vacio").hidden = cuerpo.children.length > 0;
    };
    const agregar = (p, cantidad = 1, costo = null) => {
      if (cuerpo.querySelector(`[data-id="${p.id}"]`)) return;
      const tr = document.createElement("tr");
      tr.dataset.id = p.id;
      tr.innerHTML = `<td>${esc(p.nombre)}<input type="hidden" name="lineas-producto" value="${p.id}"></td>
        <td data-titulo="Cantidad"><input name="lineas-cantidad" type="number" min="0" step="any" value="${cantidad}" required></td>
        <td data-titulo="Costo unit."><input name="lineas-costo" type="number" min="0" step="any" value="${costo ?? p.costo ?? ""}"></td>
        ${conVencimiento ? '<td data-titulo="Vence"><input name="lineas-vencimiento" type="date"></td>' : ""}
        <td class="num subtotal" data-titulo="Subtotal"></td>
        <td><button type="button" class="enlace" aria-label="Quitar">✕</button></td>`;
      tr.querySelector("button").onclick = () => { tr.remove(); recalcular(); };
      tr.querySelectorAll("input").forEach((i) => i.addEventListener("input", recalcular));
      cuerpo.append(tr);
      recalcular();
    };
    buscadorProducto(input, (p) => { agregar(p); input.value = ""; });
    (window.LINEAS_INICIALES || []).forEach((l) => agregar(l, l.cantidad, l.costo));
    recalcular();
    return { agregar };
  }

  return { editorLineas, formularioProducto, formularioMovimiento, buscadorProducto, pos, escanearCodigo };
})();
