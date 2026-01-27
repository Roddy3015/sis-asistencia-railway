let datosGlobales = [];

/* ================== LOGIN ADMIN ================== */
async function loginAdmin() {
  const usuario = document.getElementById('usuario').value;
  const password = document.getElementById('password').value;
  const errorMsg = document.getElementById('error-msg');
  errorMsg.textContent = '';

  if (!usuario || !password) {
    errorMsg.textContent = 'Ingrese usuario y contraseña';
    return;
  }

  try {
    const response = await fetch('/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario, password })
    });

    const data = await response.json();

    if (response.status === 200 && data.status === 'ok') {
      sessionStorage.setItem('adminLoggedIn', 'true');
      mostrarPanel();
    } else {
      errorMsg.textContent = 'Usuario o contraseña incorrectos';
    }
  } catch (err) {
    errorMsg.textContent = 'Error al conectarse al servidor';
    console.error(err);
  }
}

function mostrarPanel() {
  document.getElementById('login-box').style.display = 'none';
  document.querySelector('.admin-container').style.display = 'block';
  cargarReportes();
}

function logoutAdmin() {
  sessionStorage.removeItem('adminLoggedIn');
  window.location.reload();
}

window.onload = function () {
  if (sessionStorage.getItem('adminLoggedIn') === 'true') {
    mostrarPanel();
  } else {
    document.getElementById('login-box').style.display = 'flex';
    document.querySelector('.admin-container').style.display = 'none';
  }
};

/* ================== ASISTENCIAS ================== */
async function cargarReportes() {
  const response = await fetch('/admin/get_all');
  const datos = await response.json();

  datosGlobales = datos;
  renderTabla(datos);
}

async function guardarObservacion(id) {
  const textarea = document.getElementById(`obs-${id}`);
  const observacion = textarea.value;

  try {
    const response = await fetch('/admin/guardar_observacion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_asistencia: id, observacion_admin: observacion })
    });

    const result = await response.json();
    if (result.status === 'ok') {
      alert('Observación guardada correctamente');
    } else {
      alert('Error: ' + (result.message || 'No se pudo guardar'));
    }
  } catch (err) {
    console.error(err);
    alert('Error al guardar la observación');
  }
}

function renderTabla(datos) {
  const tabla = document.getElementById('lista-asistencias');
  tabla.innerHTML = "";

  datos.forEach(asist => {
    const nombresEntrada = asist.entrada.integrantes.length
      ? asist.entrada.integrantes.map(p => `• ${p.nombre}`).join('<br>')
      : '<i>Sin integrantes</i>';

    let alertaHtml = '';
    if (asist.salida.alerta) {
      asist.salida.alerta.split(' | ').forEach(p => {
        const esFalta = p.toLowerCase().includes('falta');
        alertaHtml += `<span class="tag-alerta ${esFalta ? 'tag-falta' : 'tag-nuevo'}">${p}</span>`;
      });
    }

    const horas = parseFloat(asist.horas_totales) || 0;
    const h = Math.floor(horas);
    const m = Math.round((horas - h) * 60);

    const extras = parseFloat(asist.horas_extras) || 0;
    const eh = Math.floor(extras);
    const em = Math.round((extras - eh) * 60);

    const estadoEntrada = (asist.entrada.estado || '').toLowerCase();
    const fotosEntrada = asist.entrada?.fotos || [];
    const fotosSalida = asist.salida?.fotos || [];

    tabla.innerHTML += `
      <tr>
        <td><b>${asist.fecha}</b></td>
        <td>${asist.nombre_jefe}</td>

        <td class="seccion-celda">
          <div class="info-item"><b>OC:</b> ${asist.servicio.oc || '-'}</div>
          <div class="info-item"><b>Cliente:</b> ${asist.servicio.cliente || '-'}</div>
          <div class="info-item"><b>Servicio:</b><br>${asist.servicio.descripcion || '-'}</div>
        </td>

        <td class="seccion-celda">
          <div class="info-item"><b>Hora:</b> ${asist.entrada.hora}</div>
          <div class="info-item">
            <b>Estado:</b>
            <span class="badge ${estadoEntrada}">${asist.entrada.estado || '-'}</span>
          </div>

          <div class="info-item">
            <b>Ubicación:</b>
            <a href="https://www.google.com/maps?q=${asist.entrada.ubicacion.lat},${asist.entrada.ubicacion.lon}"
               target="_blank"
               style="color:#00ff88; text-decoration:none; font-weight:bold;">
               📍Ver mapa
            </a>
          </div>

          <div class="info-item">
            <b>Fotos:</b><br>
            ${fotosEntrada[0] ? `<img src="${fotosEntrada[0]}" class="img-admin" onclick="abrirModalImagen('${fotosEntrada[0]}')" title="Ver foto">` : ''}
            ${fotosEntrada[1] ? `<img src="${fotosEntrada[1]}" class="img-admin" onclick="abrirModalImagen('${fotosEntrada[1]}')" title="Ver foto">` : ''}
          </div>

          <div class="info-item"><b>Integrantes:</b><br>${nombresEntrada}</div>
        </td>

        <td class="seccion-celda">
          ${asist.salida.hora ? `
            <div class="info-item"><b>Hora:</b> ${asist.salida.hora}</div>
            <div class="info-item"><b>Estado:</b> <span class="badge finalizado">FINALIZADO</span></div>
            <div class="info-item">
              <b>Fotos:</b><br>
              ${fotosSalida[0] ? `<img src="${fotosSalida[0]}" class="img-admin" onclick="abrirModalImagen('${fotosSalida[0]}')" title="Ver foto">` : ''}
              ${fotosSalida[1] ? `<img src="${fotosSalida[1]}" class="img-admin" onclick="abrirModalImagen('${fotosSalida[1]}')" title="Ver foto">` : ''}
            </div>
            ${alertaHtml}
          ` : '<i>Pendiente de salida</i>'}
        </td>

        <td>
          <div class="horas-txt">${h} h ${m} min</div>
          <small>Jornada Total</small>
          ${extras > 0 ? `
            <div style="margin-top:6px; color:#ffd166; font-weight:bold;">
              + ${eh} h ${em} min extras
            </div>` : ''
          }
        </td>

        <td class="seccion-celda">
          <textarea id="obs-${asist.id_asistencia}" rows="3" style="width:95%;">${asist.observacion_admin || ''}</textarea>

          ${asist.zip_descargado ? `
            <div style="margin-top:6px; padding:6px 8px; border-radius:6px; background: rgba(255, 209, 102, 0.15); color:#ffd166; font-size:12px;">
              📦 Reporte descargado${asist.zip_descargado_at ? `: ${asist.zip_descargado_at}` : ''}
            </div>` : ''
          }

          <div style="margin-top:6px;">
            <button onclick="guardarObservacion(${asist.id_asistencia})">Guardar</button>
          </div>
        </td>
      </tr>
    `;
  });
}

function buscarConFiltros() {
  const oc = document.getElementById('buscarOC').value.trim();
  const inicio = document.getElementById('fechaInicio').value;
  const fin = document.getElementById('fechaFin').value;

  if (!oc || !inicio || !fin) {
    alert('Debe ingresar OC, fecha inicio y fecha fin');
    return;
  }
  if (inicio > fin) {
    alert('La fecha inicio no puede ser mayor a la fecha fin');
    return;
  }

  const filtrados = datosGlobales.filter(a => {
    const fecha = a.fecha;
    return (
      a.servicio.oc &&
      a.servicio.oc.toLowerCase().includes(oc.toLowerCase()) &&
      fecha >= inicio &&
      fecha <= fin
    );
  });

  renderTabla(filtrados);
}

function descargarZip() {
  const oc = document.getElementById('buscarOC').value.trim();
  const inicio = document.getElementById('fechaInicio').value;
  const fin = document.getElementById('fechaFin').value;

  if (!oc || !inicio || !fin) {
    alert('Debe ingresar OC y rango de fechas para descargar');
    return;
  }
  if (inicio > fin) {
    alert('Rango de fechas inválido');
    return;
  }

  window.open(`/admin/servicios/zip?oc=${encodeURIComponent(oc)}&inicio=${inicio}&fin=${fin}`, '_blank');
}

/* ================== MODAL USUARIOS ================== */
async function abrirModalUsuarios() {
  document.getElementById('modal-usuarios').style.display = 'flex';
  await cargarUsuarios();
}

function cerrarModalUsuarios() {
  document.getElementById('modal-usuarios').style.display = 'none';
}

async function cargarUsuarios() {
  const tbody = document.getElementById('tabla-usuarios');
  tbody.innerHTML = `<tr><td colspan="5" style="padding:10px;">Cargando...</td></tr>`;

  const res = await fetch('/admin/usuarios');
  const data = await res.json();

  tbody.innerHTML = '';
  data.forEach(u => {
    const activo = parseInt(u.activo) === 1;
    const badge = activo
      ? `<span class="badge-activo-si">SI</span>`
      : `<span class="badge-activo-no">NO</span>`;

    const btnToggleClass = activo ? 'btn-users btn-users-danger' : 'btn-users btn-users-success';
    const btnToggleText = activo ? 'Desactivar' : 'Activar';

    tbody.innerHTML += `
      <tr>
        <td>${u.id_usuario}</td>
        <td>${u.nombre_completo}</td>
        <td>${u.rol}</td>
        <td>${badge}</td>
        <td>
          <div class="users-actions">
            <button class="${btnToggleClass}" onclick="toggleActivo(${u.id_usuario}, ${activo ? 0 : 1}, '${u.nombre_completo}', '${u.rol}', ${activo ? 1 : 0})">
              ${btnToggleText}
            </button>
            <button class="btn-users btn-users-info" onclick="cambiarPass(${u.id_usuario}, '${u.nombre_completo}')">
              Cambiar Contraseña
            </button>
          </div>
        </td>
      </tr>
    `;
  });
}

async function crearUsuario() {
  const nombre = document.getElementById('u-nombre').value.trim();
  const password = document.getElementById('nuevoPassword').value.trim(); // ✅ FIX
  const rol = document.getElementById('u-rol').value;
  const msg = document.getElementById('u-msg');

  msg.textContent = '';
  msg.style.color = '#fff';

  if (!nombre || !password) {
    msg.style.color = '#ff4d4d';
    msg.textContent = 'Completa nombre y contraseña.';
    return;
  }

  const res = await fetch('/admin/usuarios', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nombre_completo: nombre, password, rol })
  });

  const data = await res.json();
  if (res.status === 201) {
    msg.style.color = '#00ff88';
    msg.textContent = '✅ Usuario creado.';
    document.getElementById('u-nombre').value = '';
    document.getElementById('nuevoPassword').value = '';
    await cargarUsuarios();
  } else {
    msg.style.color = '#ff4d4d';
    msg.textContent = '❌ ' + (data.error || 'No se pudo crear.');
  }
}

async function toggleActivo(id, activo, nombre, rol, estabaActivo) {
  if (estabaActivo === 1 && activo === 0) {
    const ok = confirm(`¿Seguro que deseas DESACTIVAR a "${nombre}" (${rol})?`);
    if (!ok) return;
  }

  const res = await fetch(`/admin/usuarios/${id}/activo`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ activo })
  });

  const data = await res.json();
  if (res.status === 200) {
    await cargarUsuarios();
  } else {
    alert(data.error || 'No se pudo cambiar el estado.');
  }
}

async function cambiarPass(id, nombre) {
  const pass = prompt(`Nueva contraseña para ${nombre}:`);
  if (!pass) return;

  const res = await fetch(`/admin/usuarios/${id}/password`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: pass })
  });

  const data = await res.json();
  if (res.status === 200) {
    alert('✅ Contraseña actualizada.');
  } else {
    alert(data.error || 'No se pudo actualizar la contraseña.');
  }
}

function togglePassword() {
  const input = document.getElementById('nuevoPassword');
  input.type = input.type === 'password' ? 'text' : 'password';
}

function abrirModalImagen(src) {
  const modal = document.getElementById('modal-imagen');
  const img = document.getElementById('img-modal-src');
  if(!modal || !img) return

  img.src = src;
  modal.style.display = 'flex';
}

function cerrarModalImagen(ev) {

  const modal = document.getElementById('modal-imagen');
  const img = document.getElementById('img-modal-src');
  if(!modal || !img) return;

  if (ev && ev.target && ev.target.id !== 'modal-imagen') return;

  modal.style.display = 'none';
  img.src = '';
  
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const modal = document.getElementById('modal-imagen');
    if (modal && modal.style.display === 'flex') cerrarModalImagen();
  }
});
