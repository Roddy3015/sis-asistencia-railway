import os
import json
import pandas as pd
import requests
import io
import mysql.connector
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask import render_template
from datetime import datetime, timezone, timedelta
from datetime import time as dt_time
import zipfile
from pathlib import Path
import re

PERU_TZ = timezone(timedelta(hours=-5))
ahora_peru = datetime.now(PERU_TZ)

app = Flask(__name__)
CORS(app)

@app.get("/health")
def health():
    return {"status": "ok"}, 200


@app.route('/')
def home():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

#Conexión MySQL
def conexion_mysql():
    host = os.environ.get("MYSQLHOST")
    if not host:
        raise Exception("MYSQLHOST no definido en variables de entorno")
    
    conn = mysql.connector.connect(
        
        host=host,
        user=os.environ.get("MYSQLUSER"),
        password=os.environ.get("MYSQLPASSWORD"),
        database=os.environ.get("MYSQLDATABASE"),
        port=int(os.environ.get("MYSQLPORT", 3306))
    )
    return conn
    
from werkzeug.utils import secure_filename

def guardar_foto_local(file, subcarpeta, nombre_archivo):
    if not file:
        return None
    
    carpeta_abs = os.path.join(UPLOAD_FOLDER, subcarpeta)
    os.makedirs(carpeta_abs, exist_ok=True)
    filename = secure_filename(nombre_archivo)
    ruta_abs = os.path.join(carpeta_abs, filename)
    file.save(ruta_abs)
    return f"{subcarpeta}/{filename}"

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory('uploads', filename)

def _safe_str(s: str) -> str:
    if s is None:
        return ""
    return "".join(c for c in str(s) if c.isalnum() or c in ("-", "_")).strip("_")

def _fmt_time(valor):
    if valor is None or valor == '':
        return "00-00-00"

    if isinstance(valor, timedelta):
        total = int(valor.total_seconds())
        hh = total // 3600
        mm = (total % 3600) // 60
        ss = total % 60
        return f"{hh:02d}-{mm:02d}-{ss:02d}"

    if isinstance(valor, str):
        return valor.replace(":", "-")

    if hasattr(valor, "strftime"):
        return valor.strftime("%H-%M-%S")

    return "00-00-00"

def _zip_add_file(zf: zipfile.ZipFile, file_rel_path: str, arcname: str):
    """
    file_rel_path: ej 'entrada/xxx.jpg' (lo que guardas en BD)
    """
    if not file_rel_path:
        return None

    abs_path = Path(UPLOAD_FOLDER) / file_rel_path
    if abs_path.exists() and abs_path.is_file():
        zf.write(str(abs_path), arcname=arcname)
        return str(abs_path)  
    return None

def convertir_datetime_peru(dt):
    if not dt:
        return None

    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(PERU_TZ).strftime("%Y-%m-%d %H:%M:%S")

    if isinstance(dt, str):
        try:
            parsed = datetime.fromisoformat(dt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(PERU_TZ).strftime("%Y-%m-%d %H:%M:%S")
        except:
            return dt

    return str(dt)

#LOGIN
@app.route('/login', methods=['POST'])
def login():
    datos = request.json
    nombre = datos.get('nombre')
    password = datos.get('password')
    try:
        conn = conexion_mysql()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_usuario, nombre_completo, rol
            FROM usuarios
            WHERE nombre_completo = %s
              AND password = %s
              AND rol = 'JEFE'
              AND activo = 1
        """, (nombre, password))

        usuario = cursor.fetchone()
        conn.close()

        if usuario:
            return jsonify({"status": "success", "id_usuario": usuario["id_usuario"], "nombre": usuario["nombre_completo"]}), 200
        return jsonify({"status": "error", "message": "Credenciales invalidas o no es JEFE"}), 401
    except Exception as e:
        print("ERROR LOGIN: ", e)
        return jsonify({"status": "error", "message": str(e)}), 500

#REGISTRO GRUPAL
@app.route('/registrar_grupal', methods=['POST'])
def registrar_grupal():
    try:
        id_lider = request.form.get('id_lider')
        tipo = request.form.get('tipo_evento')
        integrantes = json.loads(request.form.get('integrantes'))
        lat = request.form.get('lat')
        lon = request.form.get('lon')
        foto_grupo = request.files.get('foto_grupal')
        foto_doc = request.files.get('foto_documento')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        conn = conexion_mysql()
        cursor = conn.cursor()
        alerta_msg = None
        
        if tipo == 'ENTRADA':  
            oc_ref = request.form.get('oc_referencia')
            if not oc_ref:
                return jsonify({"status": "error", "message": "Debe seleccionar un servicio (OC)"}), 400
            
            ahora_peru = datetime.now(PERU_TZ)
            ahora = ahora_peru.time()
            limite = datetime.strptime("08:15:00", "%H:%M:%S").time()
            estado = "TEMPRANO" if ahora <= limite else "TARDANZA"
            stamp = ahora_peru.strftime("%Y-%m-%d_%H-%M-%S")
            try:
                path_grupo = guardar_foto_local(foto_grupo, "entrada", f"{stamp}_{oc_ref}_entrada_grupal.jpg")
                path_doc = guardar_foto_local( foto_doc, "entrada",f"{stamp}_{oc_ref}_entrada_documento.jpg")
            except Exception as e:
                return jsonify({"status": "error", "message": f"Error al guardar imágenes: {e}"}), 500
            
            print("INSERTAR ASISTENCIA: ", id_lider, tipo, lat, lon, path_grupo, path_doc, estado, oc_ref, "Integrantes:", integrantes)

            try:
                fecha_peru = ahora_peru.date()
                hora_peru = ahora_peru.time()

                cursor.execute("""
                    INSERT INTO asistencias
                    (id_lider, tipo_registro, fecha, hora, latitud, longitud,
                    foto_grupal_path, foto_documento_path, estado_asistencia, oc_referencia)
                    VALUES (%s, 'ENTRADA', %s, %s, %s, %s, %s, %s, %s, %s)
                """, (id_lider, fecha_peru, hora_peru, lat, lon, path_grupo, path_doc, estado, oc_ref))

                id_asistencia = cursor.lastrowid

                for p in integrantes:
                    cursor.execute("""
                        INSERT INTO detalle_asistencia
                        (id_asistencia, nombre_integrante, dni, cargo)
                        VALUES (%s, %s, %s, %s)
                    """, (id_asistencia, p['nombre'], p['dni'], p['cargo']))

            except mysql.connector.Error as e:
                print("ERROR: MYSQL", e)
                conn.rollback()
                conn.close()
                return jsonify({"status": "error", "message": f"Error en base de datos: {e}"}), 500
            
        else:  #SALIDA
            
            oc_ref = request.form.get('oc_referencia')
            if not oc_ref:
                return jsonify({
                    "status": "error",
                    "message": "Debe seleccionar un OC para la salida"
                }), 400
            
            ahora_peru = datetime.now(PERU_TZ)
            hoy_peru = ahora_peru.date()
            hora_salida_peru = ahora_peru.time()
            
            cursor.execute("""
                SELECT id_asistencia, fecha, hora
                FROM asistencias
                WHERE id_lider = %s
                  AND fecha = %s
                  AND tipo_registro = 'ENTRADA'
                  AND hora_salida IS NULL
                  AND oc_referencia = %s
                ORDER BY hora ASC
                LIMIT 1
            """, (id_lider, hoy_peru, oc_ref))

            registro = cursor.fetchone()

            if not registro:
                return jsonify({
                    "status": "error",
                    "message": "No hay una entrada abierta para este OC hoy"
                }), 400

            id_asist_ent = registro[0]
            fecha_ent = registro[1]
            hora_ent = registro[2]
            
            if isinstance(hora_ent, timedelta):
                total = int(hora_ent.total_seconds())
                h = (total // 3600) % 24
                m = (total % 3600) // 60
                s = total % 60
                hora_ent = dt_time(h, m, s)

            dt_entrada = datetime.combine(fecha_ent, hora_ent).replace(tzinfo=PERU_TZ)
            dt_salida = datetime.now(PERU_TZ)

            minutos_totales = max(0, int((dt_salida - dt_entrada).total_seconds() // 60))
            horas_totales = round(minutos_totales / 60, 2)
            horas_extras = max(0, horas_totales - 8)

            cursor.execute("SELECT dni, nombre_integrante FROM detalle_asistencia WHERE id_asistencia = %s", (id_asist_ent,))
            filas = cursor.fetchall()
            dict_ent = {r[0]: r[1] for r in filas}
            dnis_ent = set(dict_ent.keys())
            dnis_sal = set(p['dni'] for p in integrantes)
            dict_sal = {p['dni']: p['nombre'] for p in integrantes}

            mensajes = []
            if dnis_ent - dnis_sal:
                mensajes.append("Falta: " + ", ".join(dict_ent[d] for d in dnis_ent - dnis_sal))
            if dnis_sal - dnis_ent:
                mensajes.append("Nuevo: " + ", ".join(dict_sal[d] for d in dnis_sal - dnis_ent))

            alerta_msg = " | ".join(mensajes) if mensajes else None

            stamp = ahora_peru.strftime("%Y-%m-%d_%H-%M-%S")
            path_grupo_sal = None
            path_doc_sal = None

            if foto_grupo:
                path_grupo_sal = guardar_foto_local(
                    foto_grupo,
                    "salida",
                    f"{stamp}_{oc_ref}_salida_grupal.jpg"
                )

            if foto_doc:
                path_doc_sal = guardar_foto_local(
                    foto_doc,
                    "salida",
                    f"{stamp}_{oc_ref}_salida_documento.jpg"
                )

            cursor.execute("""
                UPDATE asistencias SET
                    hora_salida = %s,
                    foto_grupal_salida_path = %s,
                    foto_doc_salida_path = %s,
                    estado_salida = 'FINALIZADO',
                    horas_trabajadas = %s,
                    horas_extras = %s,
                    observacion_personal = %s,
                    integrantes_salida = %s
                        
                WHERE id_asistencia = %s
            """, (hora_salida_peru, path_grupo_sal, path_doc_sal, horas_totales, horas_extras, alerta_msg,
                  json.dumps(integrantes), id_asist_ent))

        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "tipo": tipo, "alerta": alerta_msg}), 200

    except Exception as e:
        print("ERROR GENERAL REGISTRAR GRUPAL: ", e)
        return jsonify({"error": str(e)}), 500
    
import pandas as pd
from flask import send_file
from io import BytesIO

#ADMIN
@app.route('/admin/get_all', methods=['GET'])
def get_all_reports():
    try:
        conn = conexion_mysql()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT A.fecha, U.nombre_completo, 
                   A.hora, A.hora_salida,
                   A.estado_asistencia, A.estado_salida,
                   A.foto_grupal_path, A.foto_documento_path,
                   A.foto_grupal_salida_path, A.foto_doc_salida_path,
                   A.horas_trabajadas, A.observacion_personal,
                   A.id_asistencia, A.integrantes_salida,
                   A.latitud, A.longitud, A.oc_referencia,
                   S.cliente, S.descripcion,
                   A.observacion_admin,
                   A.horas_extras,
                   A.zip_descargado,
                   A.zip_descargado_at
                       
            FROM asistencias A
            JOIN usuarios U ON A.id_lider = U.id_usuario
            LEFT JOIN servicios S ON A.oc_referencia = S.oc
            WHERE A.tipo_registro = 'ENTRADA'
            ORDER BY A.fecha DESC, A.hora DESC
        """)
        rows = cursor.fetchall()
        resultados = []

        def convertir_hora(valor):
            if valor is None or valor == '':
                return None
                
            if isinstance(valor, timedelta):
                total = int(valor.total_seconds())
                h = (total // 3600) % 24
                m = (total % 3600) // 60
                s = total % 60
                valor = dt_time(h, m, s)

            if isinstance(valor, dt_time):
                return valor.strftime("%H:%M:%S")
            
            return str(valor)
        
        for r in rows:
            cursor.execute(
                "SELECT nombre_integrante, dni, cargo FROM detalle_asistencia WHERE id_asistencia = %s",
                (r['id_asistencia'],)
            )
            detalles = cursor.fetchall()
            integrantes_ent = [{"nombre": d['nombre_integrante'], "dni": d['dni'], "cargo": d['cargo']} for d in detalles]
            integrantes_sal = json.loads(r['integrantes_salida']) if r['integrantes_salida'] else []
            hora_peru = convertir_hora(r['hora'])
            hora_salida_peru = convertir_hora(r['hora_salida'])
            zdt = r.get("zip_descargado_at")
            zip_at = zdt.strftime("%Y-%m-%d %H:%M:%S") if zdt else None

            resultados.append({
                "fecha": str(r['fecha']),
                "nombre_jefe": r['nombre_completo'],

                "servicio": {
                    "oc": r['oc_referencia'],
                    "cliente": r['cliente'],
                    "descripcion": r['descripcion']
                },
                "entrada": {
                    "hora": hora_peru,
                    "estado": r['estado_asistencia'],
                    "fotos": [
                        f"/uploads/{r['foto_grupal_path']}" if r['foto_grupal_path'] else None,
                        f"/uploads/{r['foto_documento_path']}" if r['foto_documento_path'] else None
                    ],
                    "integrantes": integrantes_ent,
                    "ubicacion": {"lat": r['latitud'], "lon": r['longitud']}
                },
                "salida": {
                    "hora": hora_salida_peru,
                    "fotos": [
                        f"/uploads/{r['foto_grupal_salida_path']}" if r['foto_grupal_salida_path'] else None,
                        f"/uploads/{r['foto_doc_salida_path']}" if r['foto_doc_salida_path'] else None
                    ],
                    "alerta": r['observacion_personal'],
                    "integrantes": integrantes_sal
                },
                "horas_totales": r['horas_trabajadas'],
                "horas_extras": r['horas_extras'],
                "observacion_admin": r['observacion_admin'] or "",
                "id_asistencia":int(r['id_asistencia']) if r['id_asistencia'] is not None else None,
                "zip_descargado": int(r.get("zip_descargado") or 0),
                "zip_descargado_at": zip_at


            })

        conn.close()
        return jsonify(resultados), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/guardar_observacion', methods=['POST'])
def guardar_observacion_admin():
    try:
        data = request.json
        id_asistencia = data.get('id_asistencia')
        observacion = data.get('observacion_admin')

        if id_asistencia is None:
            return jsonify({"status": "error", "message": "ID inválido"}), 400

        conn = conexion_mysql()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE asistencias
            SET observacion_admin = %s
            WHERE id_asistencia = %s
        """, (observacion, id_asistencia))

        conn.commit()
        conn.close()

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/servicios/buscar', methods=['GET'])
def buscar_servicios():
    try:
        q = request.args.get('q', '').strip()

        if len(q) < 2:
            return jsonify([])

        conn = conexion_mysql()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT oc, cliente, descripcion
            FROM servicios
            WHERE oc LIKE %s
            ORDER BY oc
            LIMIT 10
        """, (f"%{q}%",))

        resultados = cursor.fetchall()
        conn.close()

        return jsonify(resultados), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/admin/export_excel', methods=['GET'])
def exportar_excel_por_oc():
    try:
        oc = request.args.get('oc')

        if not oc:
            return jsonify({"error": "OC requerida"}), 400

        conn = conexion_mysql()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                A.fecha,
                U.nombre_completo AS jefe_grupo,
                A.oc_referencia,
                S.cliente,
                S.descripcion AS servicio,
                       
                    GROUP_CONCAT(
                       
                        CONCAT(D.nombre_integrante, ' (', D.cargo, ')')
                        SEPARATOR ' | '
                    ) AS integrantes,

                A.estado_asistencia,        
                A.hora,
                A.hora_salida,
                A.horas_trabajadas,
                A.horas_extras,
                A.estado_salida,
                A.observacion_personal,
                A.observacion_admin,
                A.latitud,
                A.longitud,
                       
                A.foto_grupal_path,
                A.foto_documento_path,
                A.foto_grupal_salida_path,
                A.foto_doc_salida_path
                       
            FROM asistencias A
            JOIN usuarios U ON A.id_lider = U.id_usuario
            LEFT JOIN servicios S ON A.oc_referencia = S.oc
            LEFT JOIN detalle_asistencia D ON A.id_asistencia = D.id_asistencia
                       
            WHERE A.oc_referencia = %s
              AND A.tipo_registro = 'ENTRADA'
            
            GROUP BY A.id_asistencia
            ORDER BY A.fecha, A.hora
        """, (oc,))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return jsonify({"error": "No hay datos para este OC"}), 404

        df = pd.DataFrame(rows)

        df['ubicacion'] = df.apply(
            lambda r: f"https://www.google.com/maps?q={r['latitud']},{r['longitud']}"
            if pd.notna(r['latitud']) and pd.notna(r['longitud']) else '',
            axis=1
        )
        df.drop(columns=['latitud','longitud'], inplace = True)

        def formatear_hora(valor):
            if valor is None or valor == '':
                return ''

    
            if hasattr(valor, 'strftime'):
                return valor.strftime("%H:%M:%S")

    
            if isinstance(valor, str):
                return valor

            return ''
        
        def hora_excel(valor):
            if valor is None or valor == '':
                return ''

            if isinstance(valor, str):
                return valor
            
            if isinstance(valor, timedelta):
                total = int(valor.total_seconds())
                h = (total // 3600) % 24
                m = (total % 3600) // 60
                s = total % 60
                valor = dt_time(h, m, s)

            if hasattr(valor, "strftime"):
               return valor.strftime("%H:%M:%S")

            return str(valor)
        
        df['hora'] = df['hora'].apply(hora_excel)
        df['hora_salida'] = df['hora_salida'].apply(hora_excel)

        def horas_a_texto(h):
            if h is None:
                return ''
            h = float(h)
            horas = int(h)
            minutos = round((h - horas) * 60)
            return f"{horas} h {minutos} min"
        
        df['horas_trabajadas'] = df['horas_trabajadas'].apply(horas_a_texto)
        df['horas_extras'] = df['horas_extras'].apply(horas_a_texto)

        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Asistencias')

            ws = writer.book['Asistencias']

            ws.column_dimensions['A'].width = 12
            ws.column_dimensions['B'].width = 22   
            ws.column_dimensions['C'].width = 14   
            ws.column_dimensions['D'].width = 20   
            ws.column_dimensions['E'].width = 100  
            ws.column_dimensions['F'].width = 100  
            ws.column_dimensions['G'].width = 16   
            ws.column_dimensions['H'].width = 12   
            ws.column_dimensions['I'].width = 12  
            ws.column_dimensions['J'].width = 18   
            ws.column_dimensions['K'].width = 16   
            ws.column_dimensions['L'].width = 16   
            ws.column_dimensions['M'].width = 70   
            ws.column_dimensions['N'].width = 120   
            ws.column_dimensions['O'].width = 110  
            ws.column_dimensions['P'].width = 110   
            ws.column_dimensions['Q'].width = 110   
            ws.column_dimensions['R'].width = 110
            ws.column_dimensions['S'].width = 70
            
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name=f"reporte_asistencia_OC_{oc}.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/servicios/zip', methods=['GET'])
def descargar_zip_por_oc_y_rango():
    try:
        oc = (request.args.get('oc') or '').strip()
        inicio = (request.args.get('inicio') or '').strip()
        fin = (request.args.get('fin') or '').strip()        

        if not oc or not inicio or not fin:
            return jsonify({"error": "Debe enviar oc, inicio y fin"}), 400
        if inicio > fin:
            return jsonify({"error": "Rango inválido: inicio > fin"}), 400

        conn = conexion_mysql()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                A.id_asistencia,
                A.fecha,
                U.nombre_completo AS jefe_grupo,
                A.oc_referencia,
                S.cliente,
                S.descripcion AS servicio,
                       
                GROUP_CONCAT(
                    CONCAT(D.nombre_integrante, ' (', D.cargo, ')')
                    SEPARATOR ' | '                  
                ) AS integrantes,
                
                A.estado_asistencia,
                A.hora,
                A.hora_salida,
                A.horas_trabajadas,
                A.horas_extras,
                A.estado_salida,
                A.observacion_personal,
                A.observacion_admin,
                
                A.latitud,
                A.longitud,
                
                A.foto_grupal_path,
                A.foto_documento_path,
                A.foto_grupal_salida_path,
                A.foto_doc_salida_path
                       
            FROM asistencias A
            JOIN usuarios U ON A.id_lider = U.id_usuario
            LEFT JOIN servicios S ON A.oc_referencia = S.oc
            LEFT JOIN detalle_asistencia D ON A.id_asistencia = D.id_asistencia
                       
            WHERE A.tipo_registro = 'ENTRADA'
              AND A.oc_referencia = %s
              AND A.fecha BETWEEN %s AND %s
           
            GROUP BY A.id_asistencia
            ORDER BY A.fecha ASC, A.hora ASC
        """, (oc, inicio, fin))

        rows = cursor.fetchall()
        if not rows:
            conn.close()
            return jsonify({"error": "No hay datos para ese OC y rango"}), 404
        
        ids = [r["id_asistencia"] for r in rows if r.get("id_asistencia")]
        if ids:
            placeholders = ",".join(["%s"] * len(ids))
            cursor.execute(f"""
                UPDATE asistencias
                SET zip_descargado = 1,
                    zip_descargado_at = %s
                WHERE id_asistencia IN ({placeholders})
            """, ahora_peru, ids)

        conn.commit()
        conn.close()

        df = pd.DataFrame(rows)

        df['ubicacion'] = df.apply(
            lambda r: f"https://www.google.com/maps?q={r['latitud']},{r['longitud']}"
            if pd.notna(r.get('latitud')) and pd.notna(r.get('longitud')) else '',
            axis=1
        )

        df.drop(columns=['latitud', 'longitud'], inplace=True, errors='ignore')

        def hora_excel(valor):
            if valor is None or valor == '':
                return ''
            if isinstance(valor, str):
                return valor
            
            if isinstance(valor, timedelta):
                total = int(valor.total_seconds())
                h = (total // 3600) % 24
                m = (total % 3600) // 60
                s = total % 60
                valor = dt_time(h, m, s)

            if hasattr(valor, "strftime"):
                return valor.strftime("%H:%M:%S")
            
            return str(valor)
        
        df['hora'] = df['hora'].apply(hora_excel) if 'hora' in df.columns else df.get('hora')
        df['hora_salida'] = df['hora_salida'].apply(hora_excel) if 'hora_salida' in df.columns else df.get('hora_salida')
        
        def horas_a_texto(h):
            if h is None or h == '':
                return ''
            try:
                h = float(h)
            except Exception:
                return str(h)
            horas = int(h)
            minutos = round((h - horas) * 60)
            return f"{horas} h {minutos} min"
        
        if 'horas_trabajadas' in df.columns:
            df['horas_trabajadas'] = df['horas_trabajadas'].apply(horas_a_texto)
        
        if 'horas_extras' in df.columns:
            df['horas_extras'] = df['horas_extras'].apply(horas_a_texto)
                
        cols_fotos = [

            'foto_grupal_path', 'foto_documento_path',
            'foto_grupal_salida_path', "foto_doc_salida_path"
        ]
        df_excel = df.drop(columns=cols_fotos, errors='ignore')

        df_excel = df_excel.rename(columns={
            "id_asistencia": "ID",
            "fecha": "Fecha",
            "jefe_grupo": "Jefe de Grupo",
            "oc_referencia": "OC",
            "cliente": "Cliente",
            "servicio": "Servicio",
            "integrantes": "Integrantes",
            "estado_asistencia": "Estado Entrada",
            "hora": "Hora Entrada",
            "hora_salida": "Hora Salida",
            "horas_trabajadas": "Horas Trabajadas",
            "horas_extras": "Horas Extras",
            "estado_salida": "Estado Salida",
            "observacion_personal": "Observación Personal",
            "observacion_admin": "Observación Admin",
            "ubicacion": "Ubicación (Maps)"
})
            
        excel_bytes = BytesIO()
        with pd.ExcelWriter(excel_bytes, engine = "openpyxl") as writer:
            df_excel.to_excel(writer, index=False, sheet_name='Asistencias')
            ws = writer.book['Asistencias']

            for column_cells in ws.columns:
                max_len = 0
                col_letter = column_cells[0].column_letter
                for cell in column_cells:
                    v = "" if cell.value is None else str(cell.value)
                    if len(v) > max_len:
                        max_len = len(v)
                ws.column_dimensions[col_letter].width = min(max_len + 2, 60)

        zip_bytes = BytesIO()
        fotos_para_borrar = []
        
        excel_bytes.seek(0)
        oc_clean = _safe_str(oc)

        with zipfile.ZipFile(zip_bytes, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"reporte_OC_{oc_clean}_{inicio}_al_{fin}.xlsx", excel_bytes.getvalue())

            for r in rows:
                fecha = str(r['fecha'])

                h_ent = _fmt_time(r.get('hora'))
                h_sal = _fmt_time(r.get('hora_salida'))

                f1 = r.get('foto_grupal_path')     
                f2 = r.get('foto_documento_path')

                borrado = _zip_add_file(
                    zf, f1,
                    f"fotos/{oc_clean}/{fecha}/entrada_{fecha}_{h_ent}_{oc_clean}_grupal.jpg"
                )
                if borrado: fotos_para_borrar.append(borrado)

                borrado = _zip_add_file(
                    zf, f2,
                    f"fotos/{oc_clean}/{fecha}/entrada_{fecha}_{h_ent}_{oc_clean}_documento.jpg"
                )
                if borrado: fotos_para_borrar.append(borrado)

                fs1 = r.get('foto_grupal_salida_path')
                fs2 = r.get('foto_doc_salida_path')

                borrado = _zip_add_file(
                    zf, fs1,
                    f"fotos/{oc_clean}/{fecha}/salida_{fecha}_{h_sal}_{oc_clean}_grupal.jpg"
                )
                if borrado: fotos_para_borrar.append(borrado)

                borrado = _zip_add_file(
                    zf, fs2,
                    f"fotos/{oc_clean}/{fecha}/salida_{fecha}_{h_sal}_{oc_clean}_documento.jpg"
                )
                if borrado: fotos_para_borrar.append(borrado)

        zip_bytes.seek(0)

        for abs_path in sorted(set(fotos_para_borrar)):
            try:
                p = Path(abs_path)
                if p.exists() and p.is_file():
                    p.unlink()
            except Exception as e:
                print("WARN no se pudo borrar:", abs_path, e)

        nombre_zip = f"reporte_OC_{oc_clean}_{inicio}_al_{fin}.zip"
        return send_file(
            zip_bytes,
            as_attachment=True,
            download_name=nombre_zip,
            mimetype='application/zip'
        )

    except Exception as e:
        print("ERROR ZIP:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/admin/sync_servicios', methods=['POST'])
def sync_servicios():

    token = request.headers.get("X-SYNC-TOKEN")
    expected = os.getenv("SYNC_TOKEN")

    if not expected or token != expected:
        return jsonify({"error": "No autorizado"}), 403

    try:
        FILE_ID = os.getenv("SERVICIOS_SHEET_ID")
        if not FILE_ID:
            return jsonify({"error": "SERVICIOS_SHEET_ID no definido"}), 500

        url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"

        print("Descargando Excel desde Google Drive...")
        response = requests.get(url)
        response.raise_for_status()

        df = pd.read_excel(io.BytesIO(response.content), engine='openpyxl')

        if 'Unnamed: 0' in df.columns or df.columns[0] is None:
            df.columns = df.iloc[0]
            df = df[1:]

        df.columns = [str(c).strip().upper() for c in df.columns]
        print("Columnas:", df.columns.tolist())

        conn = conexion_mysql()
        cursor = conn.cursor()

        cursor.execute("TRUNCATE TABLE servicios")

        count = 0
        for _, row in df.iterrows():
            oc = str(row.get('OC', '')).strip()
            cliente = str(row.get('CLIENTE', '')).strip()

            descripcion = row.get('DESCRIPCIÓN')
            if descripcion is None:
                descripcion = row.get('DESCRIPCION', '')
            descripcion = str(descripcion).strip()

            if oc and oc.lower() != 'nan':
                cursor.execute("""
                    INSERT INTO servicios (oc, cliente, descripcion)
                    VALUES (%s, %s, %s)
                """, (oc, cliente, descripcion))
                count += 1

        conn.commit()
        conn.close()

        return jsonify({
            "status": "ok",
            "registros": count
        })

    except Exception as e:
        print("ERROR SYNC:", e)
        return jsonify({"error": str(e)}), 500
    
@app.route('/admin/login', methods=['POST'])
def login_admin():
    data = request.json
    usuario = data.get('usuario')
    password = data.get('password')

    try:
        conn = conexion_mysql()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id_usuario
            FROM usuarios
            WHERE nombre_completo = %s
              AND password = %s
              AND rol = 'ADMIN'
              AND activo = 1
        """, (usuario, password))

        admin = cursor.fetchone()
        conn.close()

        if admin:
            return jsonify({"status": "ok"}), 200

        return jsonify({
            "status": "error",
            "message": "Acceso denegado"
        }), 401

    except Exception as e:
        print("ERROR LOGIN ADMIN:", e)
        return jsonify({"error": str(e)}), 500
    
def _correo_auto(nombre: str) -> str:
    """
    Genera un correo tipo: rodrigo@local / rodrigo2@local si ya existe.
    """
    base = (nombre or "").strip().lower()
    base = re.sub(r"[^a-z0-9\s]", "", base)
    base = re.sub(r"\s+", ".", base).strip(".")
    if not base:
        base = "user"
    return base

@app.route('/admin/usuarios', methods=['GET'])
def admin_listar_usuarios():
    try:
        conn = conexion_mysql()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id_usuario, nombre_completo, rol, activo
            FROM usuarios
            ORDER BY rol DESC, nombre_completo ASC
        """)
        rows = cursor.fetchall()
        conn.close()
        return jsonify(rows), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/admin/usuarios', methods=['POST'])
def admin_crear_usuario():
    try:
        data = request.json or {}
        nombre = (data.get("nombre_completo") or "").strip()
        password = (data.get("password") or "").strip()
        rol = (data.get("rol") or "").strip().upper()

        if not nombre or not password or rol not in ("ADMIN", "JEFE"):
            return jsonify({"error": "Datos inválidos (nombre, password, rol ADMIN/JEFE)"}), 400

        conn = conexion_mysql()
        cursor = conn.cursor()

        base = _correo_auto(nombre)
        correo = f"{base}@local"
        n = 1
        while True:
            cursor.execute("SELECT 1 FROM usuarios WHERE correo = %s LIMIT 1", (correo,))
            existe = cursor.fetchone()
            if not existe:
                break
            n += 1
            correo = f"{base}{n}@local"

        cursor.execute("""
            INSERT INTO usuarios (nombre_completo, correo, password, rol, activo)
            VALUES (%s, %s, %s, %s, 1)
        """, (nombre, correo, password, rol))

        conn.commit()
        conn.close()
        return jsonify({"status": "ok"}), 201

    except mysql.connector.Error as e:
        return jsonify({"error": f"DB: {e}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/usuarios/<int:user_id>/password', methods=['PUT'])
def admin_cambiar_password(user_id):
    try:
        data = request.json or {}
        password = (data.get("password") or "").strip()
        if not password:
            return jsonify({"error": "Password requerida"}), 400

        conn = conexion_mysql()
        cursor = conn.cursor()
        cursor.execute("UPDATE usuarios SET password=%s WHERE id_usuario=%s", (password, user_id))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/usuarios/<int:user_id>/activo', methods=['PUT'])
def admin_cambiar_activo(user_id):
    try:
        data = request.json or {}
        activo = data.get("activo", None)
        if activo not in (0, 1, True, False, "0", "1"):
            return jsonify({"error": "activo debe ser 0 o 1"}), 400

        activo = 1 if str(activo) == "1" or activo is True else 0

        conn = conexion_mysql()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id_usuario, rol, activo FROM usuarios WHERE id_usuario=%s", (user_id,))
        u = cursor.fetchone()
        if not u:
            conn.close()
            return jsonify({"error": "Usuario no encontrado"}), 404

        if u["rol"] == "ADMIN" and int(u["activo"]) == 1 and activo == 0:
            cursor.execute("SELECT COUNT(*) AS c FROM usuarios WHERE rol='ADMIN' AND activo=1")
            c = cursor.fetchone()["c"]
            if c <= 1:
                conn.close()
                return jsonify({"error": "No puedes desactivar el último ADMIN activo"}), 400

        cursor2 = conn.cursor()
        cursor2.execute("UPDATE usuarios SET activo=%s WHERE id_usuario=%s", (activo, user_id))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
