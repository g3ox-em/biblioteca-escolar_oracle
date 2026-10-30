import os, secrets, csv, io, logging, functools
from pathlib import Path
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from contextlib import contextmanager
import oracledb
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, abort, g

load_dotenv(Path(__file__).resolve().parent / '.env')
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', MAX_CONTENT_LENGTH=1024*1024)
if os.getenv('ORACLE_CLIENT_LIB_DIR'):
    oracledb.init_oracle_client(lib_dir=os.environ['ORACLE_CLIENT_LIB_DIR'])

MULTA_POR_DIA = Decimal('5.00')
MAX_PRESTAMOS_SIMULTANEOS = 3
PAGE_SIZE = 10

MODELS = {
 'categorias': ('Categorías','id_categoria', [('nombre_categoria','Nombre','text',True,50),('descripcion','Descripción','text',False,200)]),
 'autores': ('Autores','id_autor',[('nombre','Nombre','text',True,50),('apellido','Apellido','text',True,50),('nacionalidad','Nacionalidad','text',False,50)]),
 'estudiantes': ('Estudiantes','id_estudiante',[('carnet','Carnet','text',True,20),('nombre','Nombre','text',True,50),('apellido','Apellido','text',True,50),('grado_seccion','Grado y sección','text',False,30),('correo','Correo','email',False,100)]),
 'libros': ('Libros','id_libro',[('titulo','Título','text',True,150),('isbn','ISBN','text',False,20),('publicacion','Año de publicación','number',False,4),('disponible','Ejemplares disponibles','number',True,8),('id_categoria','Categoría','select',True,0)])
}

DEFAULT_ADMIN_HASH = generate_password_hash('admin123')
DEFAULT_USER_HASH = generate_password_hash('estudiante123')

@contextmanager
def db():
    if not os.getenv('DB_USER') or not os.getenv('DB_PASSWORD'):
        raise ValueError('Configura DB_USER y DB_PASSWORD en el archivo .env.')
    kwargs = dict(user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'])
    if os.getenv('DB_SID'):
        kwargs['dsn'] = oracledb.makedsn(os.getenv('DB_HOST','localhost'),int(os.getenv('DB_PORT','1521')),sid=os.environ['DB_SID'])
    else:
        kwargs['dsn'] = os.getenv('DB_DSN','localhost:1521/XEPDB1')
    con = oracledb.connect(**kwargs)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def query(con, sql, params=None):
    with con.cursor() as cur:
        cur.execute(sql, params or {})
        if not cur.description:
            return []
        names = [d[0].lower() for d in cur.description]
        return [dict(zip(names,r)) for r in cur.fetchall()]

def execute(con, sql, params=None):
    with con.cursor() as cur:
        cur.execute(sql, params or {})
        return cur.rowcount

def audit_log(con, table_name, operation, record_id, details, username=None):
    if con is None:
        return
    try:
        user_val = username or (g.user['usuario'] if hasattr(g, 'user') and g.user else 'SISTEMA')
        execute(con, "INSERT INTO auditoria (tabla_afectada, operacion, id_registro, detalles, usuario) VALUES (:t, :o, :r, :d, :u)",
                {'t': table_name, 'o': operation, 'r': record_id, 'd': details[:250] if details else None, 'u': user_val})
    except Exception:
        pass

def ensure_schema(con):
    ddl_statements = [
        """CREATE TABLE usuarios (
            id_usuario NUMBER PRIMARY KEY,
            usuario VARCHAR2(50) NOT NULL UNIQUE,
            clave_hash VARCHAR2(255) NOT NULL,
            nombre_completo VARCHAR2(100) NOT NULL,
            rol VARCHAR2(20) DEFAULT 'ESTUDIANTE' NOT NULL,
            id_estudiante NUMBER,
            fecha_creacion DATE DEFAULT SYSDATE
        )""",
        "CREATE SEQUENCE seq_usuarios START WITH 1 INCREMENT BY 1",
        """CREATE OR REPLACE TRIGGER trg_usuarios
        BEFORE INSERT ON usuarios
        FOR EACH ROW
        BEGIN
            IF :NEW.id_usuario IS NULL THEN
                :NEW.id_usuario := seq_usuarios.NEXTVAL;
            END IF;
        END;""",
        """CREATE TABLE reservas (
            id_reserva NUMBER PRIMARY KEY,
            id_estudiante NUMBER NOT NULL,
            id_libro NUMBER NOT NULL,
            fecha_reserva DATE DEFAULT SYSDATE,
            estado VARCHAR2(20) DEFAULT 'Pendiente'
        )""",
        "CREATE SEQUENCE seq_reservas START WITH 1 INCREMENT BY 1",
        """CREATE OR REPLACE TRIGGER trg_reservas
        BEFORE INSERT ON reservas
        FOR EACH ROW
        BEGIN
            IF :NEW.id_reserva IS NULL THEN
                :NEW.id_reserva := seq_reservas.NEXTVAL;
            END IF;
        END;""",
        """CREATE TABLE auditoria (
            id_auditoria NUMBER PRIMARY KEY,
            tabla_afectada VARCHAR2(30) NOT NULL,
            operacion VARCHAR2(20) NOT NULL,
            id_registro NUMBER,
            detalles VARCHAR2(255),
            fecha_hora DATE DEFAULT SYSDATE,
            usuario VARCHAR2(50) DEFAULT 'SISTEMA'
        )""",
        "CREATE SEQUENCE seq_auditoria START WITH 1 INCREMENT BY 1",
        """CREATE OR REPLACE TRIGGER trg_auditoria
        BEFORE INSERT ON auditoria
        FOR EACH ROW
        BEGIN
            IF :NEW.id_auditoria IS NULL THEN
                :NEW.id_auditoria := seq_auditoria.NEXTVAL;
            END IF;
        END;"""
    ]
    for ddl in ddl_statements:
        try:
            execute(con, ddl)
        except Exception:
            pass
    try:
        users = query(con, "SELECT COUNT(*) n FROM usuarios")
        if users and users[0]['n'] == 0:
            execute(con, "INSERT INTO usuarios (usuario, clave_hash, nombre_completo, rol) VALUES (:u, :c, :n, :r)",
                    {'u': 'admin', 'c': DEFAULT_ADMIN_HASH, 'n': 'Administrador General', 'r': 'ADMIN'})
            execute(con, "INSERT INTO usuarios (usuario, clave_hash, nombre_completo, rol) VALUES (:u, :c, :n, :r)",
                    {'u': 'estudiante', 'c': DEFAULT_USER_HASH, 'n': 'Estudiante Demo', 'r': 'ESTUDIANTE'})
    except Exception:
        pass

def integer(value, label, minimum=0):
    try:
        n = int(value)
    except (ValueError, TypeError):
        raise ValueError(f'{label}: ingresa un número entero.')
    if n < minimum:
        raise ValueError(f'{label}: mínimo {minimum}.')
    return n

def parsedate(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError('Ingresa una fecha válida.')

def check_student_eligibility(con, student):
    if con is None:
        return
    overdue = query(con, "SELECT COUNT(*) n FROM prestamos WHERE id_estudiante=:s AND estado<>'Devuelto' AND fecha_limite<TRUNC(SYSDATE)", {'s': student})
    if overdue and overdue[0]['n'] > 0:
        raise ValueError('El estudiante tiene préstamos atrasados pendientes. Debe solventar antes de un nuevo préstamo.')
    active = query(con, "SELECT COUNT(*) n FROM prestamos WHERE id_estudiante=:s AND estado<>'Devuelto'", {'s': student})
    if active and active[0]['n'] >= MAX_PRESTAMOS_SIMULTANEOS:
        raise ValueError(f'El estudiante ya alcanzó el límite máximo permitido de {MAX_PRESTAMOS_SIMULTANEOS} préstamos simultáneos.')

def new_loan(con, student, book, start, limit):
    if limit < start: raise ValueError('La fecha límite no puede ser anterior al préstamo.')
    if start > date.today(): raise ValueError('El préstamo no puede tener fecha futura.')
    if con is not None:
        check_student_eligibility(con, student)
    if execute(con,'UPDATE libros SET disponible=disponible-1 WHERE id_libro=:b AND disponible>=1',{'b':book}) != 1:
        raise ValueError('El libro no existe o no tiene ejemplares disponibles.')
    state = 'Atrasado' if limit < date.today() else 'Activo'
    execute(con,"INSERT INTO prestamos(id_estudiante,id_libro,fecha_prestamo,fecha_limite,estado) VALUES(:s,:b,:f,:l,:e)",{'s':student,'b':book,'f':start,'l':limit,'e':state})
    audit_log(con, 'PRESTAMOS', 'INSERT', None, f'Prestamo de libro {book} a estudiante {student}')

def return_loan(con, loan, returned, notes, damage):
    rows=query(con,'SELECT id_libro,fecha_prestamo,fecha_limite,estado FROM prestamos WHERE id_prestamo=:p FOR UPDATE',{'p':loan})
    if not rows: raise ValueError('Préstamo no encontrado.')
    row=rows[0]
    if row['estado']=='Devuelto' or query(con,'SELECT id_devolucion FROM devoluciones WHERE id_prestamo=:p',{'p':loan}):
        raise ValueError('Este préstamo ya fue devuelto.')
    f_prestamo = row['fecha_prestamo'].date() if isinstance(row['fecha_prestamo'], datetime) else row['fecha_prestamo']
    if returned < f_prestamo or returned > date.today():
        raise ValueError('La devolución debe estar entre la fecha del préstamo y hoy.')
    limit = row.get('fecha_limite')
    if isinstance(limit, datetime):
        limit = limit.date()
    elif not limit:
        limit = returned
    fine=MULTA_POR_DIA*max(0,(returned-limit).days)+damage
    if fine>Decimal('9999.99'): raise ValueError('La multa total no puede superar Q9,999.99.')
    execute(con,'INSERT INTO devoluciones(id_prestamo,fecha_devolucion,observaciones,monto_multa) VALUES(:p,:f,:o,:m)',{'p':loan,'f':returned,'o':notes,'m':fine})
    execute(con,"UPDATE prestamos SET estado='Devuelto' WHERE id_prestamo=:p",{'p':loan})
    execute(con,'UPDATE libros SET disponible=NVL(disponible,0)+1 WHERE id_libro=:b',{'b':row['id_libro']})
    audit_log(con, 'DEVOLUCIONES', 'INSERT', loan, f'Devolucion prestamo {loan}. Multa Q{fine}')

def renew_loan(con, loan, days=7):
    rows = query(con, 'SELECT id_prestamo, fecha_limite, estado FROM prestamos WHERE id_prestamo=:p FOR UPDATE', {'p': loan})
    if not rows:
        raise ValueError('Préstamo no encontrado.')
    row = rows[0]
    if row['estado'] == 'Devuelto':
        raise ValueError('No se puede renovar un préstamo ya devuelto.')
    val = row['fecha_limite']
    limit = val.date() if isinstance(val, datetime) else val
    if limit and limit < date.today():
        raise ValueError('No se puede renovar un préstamo que ya se encuentra atrasado.')
    new_limit = limit + timedelta(days=days)
    execute(con, "UPDATE prestamos SET fecha_limite=:nl WHERE id_prestamo=:p", {'nl': new_limit, 'p': loan})
    audit_log(con, 'PRESTAMOS', 'RENOVACION', loan, f'Prestamo extendido {days} dias hasta {new_limit.isoformat()}')

def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.user:
            flash('Debes iniciar sesión para acceder a este módulo.')
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.user:
            flash('Debes iniciar sesión con rol de Administrador.')
            return redirect(url_for('login', next=request.path))
        if g.user.get('rol') != 'ADMIN':
            flash('Acceso restringido: se requieren permisos de Administrador.')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def setup_request():
    session.setdefault('csrf', secrets.token_hex(32))
    g.user = session.get('user')
    if request.method == 'POST' and not secrets.compare_digest(request.form.get('csrf', ''), session['csrf']):
        abort(400, description='Formulario vencido. Recarga la página.')

@app.context_processor
def inject_context():
    return dict(
        models=MODELS,
        today=date.today().isoformat(),
        current_user=g.user
    )

@app.errorhandler(oracledb.Error)
def oracle_error(error):
    logging.exception('Error de Oracle')
    code = getattr(error.args[0], 'code', None)
    msg_str = str(error)
    custom_messages = {
        1: 'Ya existe un registro con esos datos únicos (carnet, usuario o devolución duplicada).',
        2292: 'No se puede eliminar: el registro tiene préstamos o relaciones activas.',
        2291: 'El registro relacionado no existe. Verifica estudiante, libro o categoría.',
        942: 'No se encuentran las tablas requeridas. Ejecuta el script SQL en tu base Oracle.',
        20001: 'La fecha límite no puede ser anterior a la del préstamo.',
        20002: 'La fecha del préstamo no puede ser futura.',
        20003: 'El estudiante tiene préstamos atrasados pendientes.',
        20004: 'El estudiante superó el límite máximo de 3 préstamos permitidos.',
        20005: 'El libro no tiene existencias disponibles.',
        20010: 'Este préstamo ya fue devuelto.',
        20011: 'La fecha de devolución es inválida.',
        20020: 'No se puede renovar un préstamo ya devuelto.',
        20021: 'No se puede renovar un préstamo atrasado.'
    }
    msg = custom_messages.get(code)
    if not msg:
        for err_code, custom_text in custom_messages.items():
            if f'ORA-{err_code:05d}' in msg_str or f'ORA-{err_code}' in msg_str:
                msg = custom_text
                break
    if not msg:
        msg = 'No se pudo completar la operación en Oracle. Revisa la consola y tu conexión.'
    return render_template('error.html', message=msg), 503

@app.errorhandler(ValueError)
def value_error(error):
    return render_template('error.html', message=str(error)), 400

@app.after_request
def security_headers(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Referrer-Policy'] = 'same-origin'
    return resp

@app.route('/login', methods=['GET', 'POST'])
def login():
    if g.user:
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form.get('usuario', '').strip()
        password = request.form.get('clave', '')
        if not username or not password:
            flash('Ingresa usuario y contraseña.')
            return render_template('login.html')
        with db() as con:
            ensure_schema(con)
            rows = query(con, "SELECT id_usuario, usuario, clave_hash, nombre_completo, rol, id_estudiante FROM usuarios WHERE LOWER(usuario)=:u", {'u': username.lower()})
            if rows and check_password_hash(rows[0]['clave_hash'], password):
                u = rows[0]
                session['user'] = {
                    'id': u['id_usuario'],
                    'usuario': u['usuario'],
                    'nombre': u['nombre_completo'],
                    'rol': u['rol'],
                    'id_estudiante': u.get('id_estudiante')
                }
                flash(f'Bienvenido al sistema, {u["nombre_completo"]}.')
                audit_log(con, 'USUARIOS', 'LOGIN', u['id_usuario'], 'Inicio de sesion exitoso', u['usuario'])
                next_url = request.args.get('next')
                return redirect(next_url if next_url and next_url.startswith('/') else url_for('home'))
            if not rows and username.lower() == 'admin' and password == 'admin123':
                session['user'] = {
                    'id': 1,
                    'usuario': 'admin',
                    'nombre': 'Administrador General',
                    'rol': 'ADMIN',
                    'id_estudiante': None
                }
                flash('Bienvenido Administrador.')
                return redirect(url_for('home'))
            flash('Usuario o contraseña incorrectos.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    user = session.pop('user', None)
    if user:
        try:
            with db() as con:
                audit_log(con, 'USUARIOS', 'LOGOUT', user.get('id'), 'Cierre de sesion', user.get('usuario'))
        except Exception:
            pass
    flash('Has cerrado sesión.')
    return redirect(url_for('login'))

@app.route('/')
def home():
    with db() as con:
        ensure_schema(con)
        stats = {table: query(con, f'SELECT COUNT(*) n FROM {table}')[0]['n'] for table in ('libros', 'estudiantes', 'prestamos')}
        stats['disponibles'] = query(con, 'SELECT NVL(SUM(disponible),0) n FROM libros')[0]['n']
        stats['pendientes'] = query(con, "SELECT COUNT(*) n FROM prestamos WHERE estado<>'Devuelto'")[0]['n']
        stats['atrasados'] = query(con, "SELECT COUNT(*) n FROM prestamos WHERE estado<>'Devuelto' AND fecha_limite<TRUNC(SYSDATE)")[0]['n']
        stats['activos'] = max(0, stats['pendientes'] - stats['atrasados'])
        stats['devueltos'] = max(0, stats['prestamos'] - stats['pendientes'])
        res_count = query(con, "SELECT COUNT(*) n FROM reservas WHERE estado='Pendiente'")
        stats['reservas'] = res_count[0]['n'] if res_count else 0
        top_books = query(con, """SELECT l.titulo, COUNT(p.id_prestamo) n 
                                  FROM libros l LEFT JOIN prestamos p ON l.id_libro=p.id_libro 
                                  GROUP BY l.id_libro, l.titulo 
                                  ORDER BY n DESC, l.titulo ASC""")[:5]
        stats['top_books'] = top_books
    return render_template('home.html', stats=stats)

@app.route('/catalogo/<table>')
def listing(table):
    if table not in MODELS: abort(404)
    label, pk, fields = MODELS[table]
    term = request.args.get('q', '').strip()
    page = max(1, integer(request.args.get('page', 1), 'Página', 1))
    conditions = ' OR '.join(f'LOWER({f[0]}) LIKE :q' for f in fields if f[2] in ('text', 'email'))
    where_sql = f' WHERE {conditions}' if term else ''
    params = {'q': '%' + term.lower() + '%'} if term else {}
    with db() as con:
        total_rows = query(con, f'SELECT COUNT(*) n FROM {table}{where_sql}', params)[0]['n']
        offset = (page - 1) * PAGE_SIZE
        paged_sql = f"""SELECT * FROM {table}{where_sql} 
                        ORDER BY {pk} DESC 
                        OFFSET {offset} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY"""
        rows = query(con, paged_sql, params)
    total_pages = max(1, int((total_rows + PAGE_SIZE - 1) / PAGE_SIZE))
    return render_template('listing.html', table=table, label=label, pk=pk, fields=fields, rows=rows,
                           term=term, page=page, total_pages=total_pages, total_rows=total_rows)

@app.route('/catalogo/<table>/editar', methods=['GET', 'POST'])
@app.route('/catalogo/<table>/editar/<int:ident>', methods=['GET', 'POST'])
@admin_required
def edit(table, ident=None):
    if table not in MODELS: abort(404)
    label, pk, fields = MODELS[table]
    with db() as con:
        rows = query(con, f'SELECT * FROM {table} WHERE {pk}=:i', {'i': ident}) if ident else []
        if ident and not rows: abort(404)
        row = rows[0] if rows else {}
        categories = query(con, 'SELECT id_categoria, nombre_categoria FROM categorias ORDER BY nombre_categoria') if table == 'libros' else []
        authors = query(con, "SELECT id_autor, nombre||' '||apellido nombre FROM autores ORDER BY nombre") if table == 'libros' else []
        selected = [r['id_autor'] for r in query(con, 'SELECT id_autor FROM libro_autor WHERE id_libro=:i', {'i': ident})] if table == 'libros' and ident else []
        if request.method == 'POST':
            cat_id = None
            if table == 'libros':
                nueva_cat_nom = request.form.get('nueva_categoria', '').strip()
                if nueva_cat_nom:
                    if len(nueva_cat_nom) > 50:
                        raise ValueError('Nombre de categoría: máximo 50 caracteres.')
                    existing_cat = query(con, "SELECT id_categoria FROM categorias WHERE LOWER(nombre_categoria)=:n", {'n': nueva_cat_nom.lower()})
                    if existing_cat:
                        cat_id = existing_cat[0]['id_categoria']
                    else:
                        with con.cursor() as cur:
                            out = cur.var(oracledb.NUMBER)
                            cur.execute("INSERT INTO categorias (nombre_categoria, descripcion) VALUES (:n, :d) RETURNING id_categoria INTO :out",
                                        {'n': nueva_cat_nom, 'd': request.form.get('nueva_categoria_desc', '').strip()[:200] or None, 'out': out})
                            cat_id = int(out.getvalue()[0])
                        audit_log(con, 'CATEGORIAS', 'INSERT', cat_id, f'Creada nueva categoria {nueva_cat_nom}')
            data = {}
            for name, title, kind, required, length in fields:
                value = request.form.get(name, '').strip()
                if table == 'libros' and name == 'id_categoria' and cat_id:
                    value = str(cat_id)
                if required and not value: raise ValueError(f'{title} es obligatorio.')
                if kind in ('number', 'select') and value:
                    value = integer(value, title, 1 if kind == 'select' else 0)
                    if name == 'publicacion' and not 1 <= value <= 9999: raise ValueError('Año inválido.')
                    if name == 'disponible' and value > 99999999: raise ValueError('Cantidad demasiado grande.')
                elif length and len(value) > length: raise ValueError(f'{title}: máximo {length} caracteres.')
                data[name] = value if value != '' else None
            if ident:
                data['i'] = ident
                execute(con, f"UPDATE {table} SET " + ','.join(f'{f[0]}=:{f[0]}' for f in fields) + f' WHERE {pk}=:i', data)
                audit_log(con, table.upper(), 'UPDATE', ident, f'Actualizado registro en {table}')
            else:
                with con.cursor() as cur:
                    out = cur.var(oracledb.NUMBER)
                    cur.execute(f"INSERT INTO {table} (" + ','.join(data) + ') VALUES(' + ','.join(':' + k for k in data) + f') RETURNING {pk} INTO :out', dict(data, out=out))
                    ident = int(out.getvalue()[0])
                audit_log(con, table.upper(), 'INSERT', ident, f'Creado nuevo registro en {table}')
            if table == 'libros':
                author_ids = set()
                for author in request.form.getlist('autores'):
                    if author:
                        author_ids.add(integer(author, 'Autor', 1))
                nuevo_autor_nom = request.form.get('nuevo_autor_nombre', '').strip()
                nuevo_autor_ape = request.form.get('nuevo_autor_apellido', '').strip()
                if nuevo_autor_nom or nuevo_autor_ape:
                    if not nuevo_autor_nom or not nuevo_autor_ape:
                        raise ValueError('Para registrar un nuevo autor ingresa tanto el nombre como el apellido.')
                    if len(nuevo_autor_nom) > 50 or len(nuevo_autor_ape) > 50:
                        raise ValueError('Nombre y apellido del autor: máximo 50 caracteres cada uno.')
                    existing_aut = query(con, "SELECT id_autor FROM autores WHERE LOWER(nombre)=:n AND LOWER(apellido)=:a",
                                         {'n': nuevo_autor_nom.lower(), 'a': nuevo_autor_ape.lower()})
                    if existing_aut:
                        author_ids.add(existing_aut[0]['id_autor'])
                    else:
                        with con.cursor() as cur:
                            out = cur.var(oracledb.NUMBER)
                            cur.execute("INSERT INTO autores (nombre, apellido, nacionalidad) VALUES (:n, :a, :nac) RETURNING id_autor INTO :out",
                                        {'n': nuevo_autor_nom, 'a': nuevo_autor_ape, 'nac': request.form.get('nuevo_autor_nacionalidad', '').strip()[:50] or None, 'out': out})
                            new_aut_id = int(out.getvalue()[0])
                        audit_log(con, 'AUTORES', 'INSERT', new_aut_id, f'Creado nuevo autor {nuevo_autor_nom} {nuevo_autor_ape}')
                        author_ids.add(new_aut_id)
                execute(con, 'DELETE FROM libro_autor WHERE id_libro=:i', {'i': ident})
                for a_id in author_ids:
                    execute(con, 'INSERT INTO libro_autor(id_libro,id_autor) VALUES(:i,:a)', {'i': ident, 'a': a_id})
            flash('Registro guardado correctamente.')
            return redirect(url_for('listing', table=table))
    return render_template('edit.html', table=table, label=label, fields=fields, row=row, categories=categories, authors=authors, selected=selected)

@app.post('/catalogo/<table>/eliminar/<int:ident>')
@admin_required
def delete(table, ident):
    if table not in MODELS: abort(404)
    with db() as con:
        if table == 'libros': execute(con, 'DELETE FROM libro_autor WHERE id_libro=:i', {'i': ident})
        if table == 'autores': execute(con, 'DELETE FROM libro_autor WHERE id_autor=:i', {'i': ident})
        execute(con, f'DELETE FROM {table} WHERE {MODELS[table][1]}=:i', {'i': ident})
        audit_log(con, table.upper(), 'DELETE', ident, f'Eliminado ID {ident} en {table}')
    flash('Registro eliminado.')
    return redirect(url_for('listing', table=table))

LOAN_SQL = """SELECT p.id_prestamo, e.carnet, e.nombre||' '||e.apellido estudiante, l.titulo,
p.fecha_prestamo, p.fecha_limite,
CASE WHEN p.estado='Devuelto' THEN 'Devuelto' WHEN p.fecha_limite<TRUNC(SYSDATE) THEN 'Atrasado' ELSE p.estado END estado,
d.fecha_devolucion, d.monto_multa, d.observaciones
FROM prestamos p JOIN estudiantes e ON e.id_estudiante=p.id_estudiante
JOIN libros l ON l.id_libro=p.id_libro LEFT JOIN devoluciones d ON d.id_prestamo=p.id_prestamo"""

def loan_rows(con, paged=False, page=1):
    clauses = []; params = {}
    term = request.args.get('q', '').strip()
    if term:
        clauses.append("(LOWER(l.titulo) LIKE :q OR LOWER(e.carnet) LIKE :q OR LOWER(e.nombre||' '||e.apellido) LIKE :q)")
        params['q'] = '%' + term.lower() + '%'
    state = request.args.get('estado', '')
    if state == 'Devuelto': clauses.append("p.estado='Devuelto'")
    elif state == 'Atrasado': clauses.append("p.estado<>'Devuelto' AND p.fecha_limite<TRUNC(SYSDATE)")
    elif state == 'Activo': clauses.append("p.estado<>'Devuelto' AND (p.fecha_limite>=TRUNC(SYSDATE) OR p.fecha_limite IS NULL)")
    for key, op in [('desde', '>='), ('hasta', '<=')]:
        if request.args.get(key):
            clauses.append(f'TRUNC(p.fecha_prestamo){op}:{key}')
            params[key] = parsedate(request.args[key])
    if 'desde' in params and 'hasta' in params and params['desde'] > params['hasta']:
        raise ValueError('Rango de fechas inválido.')
    where_expr = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    if paged:
        count_sql = f"SELECT COUNT(*) n FROM prestamos p JOIN estudiantes e ON e.id_estudiante=p.id_estudiante JOIN libros l ON l.id_libro=p.id_libro LEFT JOIN devoluciones d ON d.id_prestamo=p.id_prestamo{where_expr}"
        total_rows = query(con, count_sql, params)[0]['n']
        offset = (page - 1) * PAGE_SIZE
        query_sql = f"{LOAN_SQL}{where_expr} ORDER BY p.id_prestamo DESC OFFSET {offset} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY"
        return query(con, query_sql, params), total_rows
    return query(con, LOAN_SQL + where_expr + ' ORDER BY p.id_prestamo DESC', params)

@app.get('/prestamos')
def loans():
    page = max(1, integer(request.args.get('page', 1), 'Página', 1))
    with db() as con:
        rows, total_rows = loan_rows(con, paged=True, page=page)
    total_pages = max(1, int((total_rows + PAGE_SIZE - 1) / PAGE_SIZE))
    return render_template('loans.html', rows=rows, page=page, total_pages=total_pages, total_rows=total_rows)

@app.route('/prestamos/nuevo', methods=['GET', 'POST'])
@admin_required
def loan_create():
    with db() as con:
        if request.method == 'POST':
            new_loan(con, integer(request.form.get('estudiante'), 'Estudiante', 1), integer(request.form.get('libro'), 'Libro', 1), parsedate(request.form.get('fecha')), parsedate(request.form.get('limite')))
            flash('Préstamo registrado. Existencias actualizadas con éxito.')
            return redirect(url_for('loans'))
        students = query(con, "SELECT id_estudiante, carnet||' · '||nombre||' '||apellido nombre FROM estudiantes ORDER BY nombre")
        books = query(con, 'SELECT id_libro, titulo, disponible FROM libros WHERE disponible>0 ORDER BY titulo')
    return render_template('loan_new.html', students=students, books=books)

@app.route('/prestamos/renovar/<int:ident>', methods=['POST'])
@admin_required
def loan_renew(ident):
    with db() as con:
        renew_loan(con, ident, 7)
        flash(f'Préstamo #{ident} renovado por 7 días adicionales.')
    return redirect(url_for('loans'))

@app.route('/devolver/<int:ident>', methods=['GET', 'POST'])
@admin_required
def return_create(ident):
    with db() as con:
        if request.method == 'POST':
            try: fine = Decimal(request.form.get('multa', '0'))
            except InvalidOperation: raise ValueError('Multa inválida.')
            if not fine.is_finite() or fine < 0 or fine > Decimal('9999.99') or fine != fine.quantize(Decimal('.01')):
                raise ValueError('Multa: de 0 a 9999.99 con máximo dos decimales.')
            notes = request.form.get('observaciones', '').strip()
            if len(notes) > 200: raise ValueError('Observaciones: máximo 200 caracteres.')
            return_loan(con, ident, parsedate(request.form.get('fecha')), notes, fine)
            flash('Devolución registrada. Ejemplar disponible nuevamente.')
            return redirect(url_for('loans'))
        rows = query(con, LOAN_SQL + ' WHERE p.id_prestamo=:i', {'i': ident})
        if not rows: abort(404)
        if rows[0]['estado'] == 'Devuelto': raise ValueError('Este préstamo ya fue devuelto.')
    return render_template('return.html', row=rows[0])

@app.route('/reservas', methods=['GET', 'POST'])
def book_reservations():
    with db() as con:
        ensure_schema(con)
        if request.method == 'POST':
            if not g.user:
                flash('Inicia sesión para reservar un libro.')
                return redirect(url_for('login'))
            student_id = integer(request.form.get('estudiante'), 'Estudiante', 1)
            book_id = integer(request.form.get('libro'), 'Libro', 1)
            book_info = query(con, "SELECT disponible, titulo FROM libros WHERE id_libro=:b", {'b': book_id})
            if not book_info:
                raise ValueError('Libro no encontrado.')
            if book_info[0]['disponible'] > 0:
                flash(f'El libro "{book_info[0]["titulo"]}" tiene ejemplares disponibles. Puedes prestarlo directamente.')
                return redirect(url_for('loan_create'))
            existing = query(con, "SELECT id_reserva FROM reservas WHERE id_estudiante=:s AND id_libro=:b AND estado='Pendiente'",
                             {'s': student_id, 'b': book_id})
            if existing:
                flash('Ya tienes una reserva pendiente para este libro.')
                return redirect(url_for('book_reservations'))
            execute(con, "INSERT INTO reservas (id_estudiante, id_libro, estado) VALUES (:s, :b, 'Pendiente')",
                    {'s': student_id, 'b': book_id})
            audit_log(con, 'RESERVAS', 'INSERT', None, f'Reserva creada para libro {book_id} por estudiante {student_id}')
            flash('Reserva realizada exitosamente. Se te notificará cuando haya un ejemplar devuelto.')
            return redirect(url_for('book_reservations'))
        reservas_rows = query(con, """SELECT r.id_reserva, r.fecha_reserva, r.estado,
                                             e.carnet, e.nombre||' '||e.apellido estudiante,
                                             l.titulo, l.disponible
                                      FROM reservas r
                                      JOIN estudiantes e ON e.id_estudiante=r.id_estudiante
                                      JOIN libros l ON l.id_libro=r.id_libro
                                      ORDER BY r.id_reserva DESC""")
        students = query(con, "SELECT id_estudiante, carnet||' · '||nombre||' '||apellido nombre FROM estudiantes ORDER BY nombre")
        books = query(con, "SELECT id_libro, titulo, disponible FROM libros ORDER BY titulo")
    return render_template('reservas.html', rows=reservas_rows, students=students, books=books)

@app.post('/reservas/cancelar/<int:ident>')
@login_required
def cancel_reservation(ident):
    with db() as con:
        execute(con, "UPDATE reservas SET estado='Cancelada' WHERE id_reserva=:i", {'i': ident})
        audit_log(con, 'RESERVAS', 'UPDATE', ident, f'Reserva #{ident} cancelada')
    flash('Reserva cancelada.')
    return redirect(url_for('book_reservations'))

@app.route('/solvencia', methods=['GET', 'POST'])
def solvencia():
    result = None
    carnet_searched = request.form.get('carnet', '').strip() or request.args.get('carnet', '').strip()
    with db() as con:
        students = query(con, "SELECT id_estudiante, carnet, nombre||' '||apellido nombre, grado_seccion, correo FROM estudiantes ORDER BY carnet")
        if carnet_searched:
            student = query(con, "SELECT id_estudiante, carnet, nombre, apellido, grado_seccion, correo FROM estudiantes WHERE carnet=:c", {'c': carnet_searched})
            if not student:
                flash('Estudiante con ese carnet no encontrado.')
            else:
                st = student[0]
                pending = query(con, """SELECT p.id_prestamo, l.titulo, p.fecha_prestamo, p.fecha_limite,
                                               CASE WHEN p.fecha_limite<TRUNC(SYSDATE) THEN 'Atrasado' ELSE p.estado END estado
                                        FROM prestamos p
                                        JOIN libros l ON l.id_libro=p.id_libro
                                        WHERE p.id_estudiante=:s AND p.estado<>'Devuelto'""", {'s': st['id_estudiante']})
                fines = query(con, """SELECT d.monto_multa, d.observaciones, d.fecha_devolucion
                                      FROM devoluciones d
                                      JOIN prestamos p ON p.id_prestamo=d.id_prestamo
                                      WHERE p.id_estudiante=:s AND d.monto_multa>0""", {'s': st['id_estudiante']})
                is_solvent = (len(pending) == 0 and len(fines) == 0)
                folio = f"SOLV-{st['carnet']}-{date.today().strftime('%Y%m%d')}"
                result = {
                    'student': st,
                    'is_solvent': is_solvent,
                    'pending_loans': pending,
                    'fines': fines,
                    'folio': folio,
                    'date_emitted': date.today().strftime('%d/%m/%Y')
                }
    return render_template('solvencia.html', students=students, result=result, carnet=carnet_searched)

@app.route('/notificaciones', methods=['GET', 'POST'])
@admin_required
def notificaciones():
    with db() as con:
        if request.method == 'POST':
            loan_id = integer(request.form.get('prestamo_id'), 'Préstamo', 1)
            loan_info = query(con, """SELECT e.nombre||' '||e.apellido estudiante, e.correo, l.titulo, p.fecha_limite
                                      FROM prestamos p
                                      JOIN estudiantes e ON e.id_estudiante=p.id_estudiante
                                      JOIN libros l ON l.id_libro=p.id_libro
                                      WHERE p.id_prestamo=:i""", {'i': loan_id})
            if loan_info:
                info = loan_info[0]
                audit_log(con, 'NOTIFICACIONES', 'EMAIL_SIMULADO', loan_id, f'Recordatorio enviado a {info["correo"]} para el libro {info["titulo"]}')
                flash(f'Recordatorio enviado exitosamente a {info["correo"]} ({info["estudiante"]}).')
            return redirect(url_for('notificaciones'))
        alerts = query(con, """SELECT p.id_prestamo, e.carnet, e.nombre||' '||e.apellido estudiante, e.correo,
                                      l.titulo, p.fecha_prestamo, p.fecha_limite,
                                      CASE WHEN p.fecha_limite<TRUNC(SYSDATE) THEN 'Atrasado' ELSE 'Por vencer' END tipo_alerta,
                                      TRUNC(SYSDATE) - TRUNC(p.fecha_limite) dias_diferencia
                               FROM prestamos p
                               JOIN estudiantes e ON e.id_estudiante=p.id_estudiante
                               JOIN libros l ON l.id_libro=p.id_libro
                               WHERE p.estado<>'Devuelto' AND p.fecha_limite <= TRUNC(SYSDATE)+2
                               ORDER BY p.fecha_limite ASC""")
    return render_template('notificaciones.html', alerts=alerts)

@app.route('/auditoria')
@admin_required
def auditoria():
    page = max(1, integer(request.args.get('page', 1), 'Página', 1))
    with db() as con:
        ensure_schema(con)
        total_rows = query(con, "SELECT COUNT(*) n FROM auditoria")[0]['n']
        offset = (page - 1) * 20
        rows = query(con, f"""SELECT id_auditoria, tabla_afectada, operacion, id_registro, detalles, fecha_hora, usuario
                              FROM auditoria
                              ORDER BY id_auditoria DESC
                              OFFSET {offset} ROWS FETCH NEXT 20 ROWS ONLY""")
    total_pages = max(1, int((total_rows + 19) / 20))
    return render_template('auditoria.html', rows=rows, page=page, total_pages=total_pages, total_rows=total_rows)

@app.get('/reportes/csv')
def export():
    with db() as con: rows = loan_rows(con)
    stream = io.StringIO(); writer = csv.writer(stream, delimiter=';')
    keys = ['id_prestamo', 'carnet', 'estudiante', 'titulo', 'fecha_prestamo', 'fecha_limite', 'estado', 'fecha_devolucion', 'monto_multa', 'observaciones']
    writer.writerow(keys)
    for row in rows:
        values = []
        for key in keys:
            value = row[key]
            if isinstance(value, datetime): value = value.strftime('%Y-%m-%d')
            value = '' if value is None else str(value)
            if value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')): value = "'" + value
            values.append(value)
        writer.writerow(values)
    return Response('\ufeff' + stream.getvalue(), mimetype='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename=prestamos_biblioteca.csv'})

if __name__ == '__main__':
    from waitress import serve
    print('Biblioteca disponible en http://127.0.0.1:5000')
    serve(app, host='127.0.0.1', port=5000)
