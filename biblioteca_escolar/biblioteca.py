import os, secrets, csv, io, logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from contextlib import contextmanager
import oracledb
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, abort

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', MAX_CONTENT_LENGTH=1024*1024)
if os.getenv('ORACLE_CLIENT_LIB_DIR'):
    oracledb.init_oracle_client(lib_dir=os.environ['ORACLE_CLIENT_LIB_DIR'])

MULTA_POR_DIA = Decimal('5.00')  # Multa por día de atraso

# Campo: nombre, etiqueta, tipo, obligatorio, longitud máxima
MODELS = {
 'categorias': ('Categorías','id_categoria', [('nombre_categoria','Nombre','text',True,50),('descripcion','Descripción','text',False,200)]),
 'autores': ('Autores','id_autor',[('nombre','Nombre','text',True,50),('apellido','Apellido','text',True,50),('nacionalidad','Nacionalidad','text',False,50)]),
 'estudiantes': ('Estudiantes','id_estudiante',[('carnet','Carnet','text',True,20),('nombre','Nombre','text',True,50),('apellido','Apellido','text',True,50),('grado_seccion','Grado y sección','text',False,30),('correo','Correo','email',False,100)]),
 'libros': ('Libros','id_libro',[('titulo','Título','text',True,150),('isbn','ISBN','text',False,20),('publicacion','Año de publicación','number',False,4),('disponible','Ejemplares disponibles','number',True,8),('id_categoria','Categoría','select',True,0)])
}

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
        names = [d[0].lower() for d in cur.description]
        return [dict(zip(names,r)) for r in cur.fetchall()]

def execute(con, sql, params=None):
    with con.cursor() as cur:
        cur.execute(sql, params or {})
        return cur.rowcount

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

def new_loan(con, student, book, start, limit):
    if limit < start: raise ValueError('La fecha límite no puede ser anterior al préstamo.')
    if start > date.today(): raise ValueError('El préstamo no puede tener fecha futura.')
    # UPDATE bloquea la fila y vuelve a validar el saldo para evitar sobrepréstamos.
    if execute(con,'UPDATE libros SET disponible=disponible-1 WHERE id_libro=:b AND disponible>=1',{'b':book}) != 1:
        raise ValueError('El libro no existe o no tiene ejemplares disponibles.')
    execute(con,"INSERT INTO prestamos(id_estudiante,id_libro,fecha_prestamo,fecha_limite,estado) VALUES(:s,:b,:f,:l,:e)",{'s':student,'b':book,'f':start,'l':limit,'e':'Atrasado' if limit < date.today() else 'Activo'})

def return_loan(con, loan, returned, notes, damage):
    rows=query(con,'SELECT id_libro,fecha_prestamo,fecha_limite,estado FROM prestamos WHERE id_prestamo=:p FOR UPDATE',{'p':loan})
    if not rows: raise ValueError('Préstamo no encontrado.')
    row=rows[0]
    if row['estado']=='Devuelto' or query(con,'SELECT id_devolucion FROM devoluciones WHERE id_prestamo=:p',{'p':loan}):
        raise ValueError('Este préstamo ya fue devuelto.')
    if returned < row['fecha_prestamo'].date() or returned > date.today():
        raise ValueError('La devolución debe estar entre la fecha del préstamo y hoy.')
    # La multa la calcula el servidor: Q5 por día de atraso + multa por daño (opcional)
    limit=row.get('fecha_limite')
    limit=limit.date() if limit else returned
    fine=MULTA_POR_DIA*max(0,(returned-limit).days)+damage
    if fine>Decimal('9999.99'): raise ValueError('La multa total no puede superar Q9,999.99.')
    execute(con,'INSERT INTO devoluciones(id_prestamo,fecha_devolucion,observaciones,monto_multa) VALUES(:p,:f,:o,:m)',{'p':loan,'f':returned,'o':notes,'m':fine})
    execute(con,"UPDATE prestamos SET estado='Devuelto' WHERE id_prestamo=:p",{'p':loan})
    execute(con,'UPDATE libros SET disponible=NVL(disponible,0)+1 WHERE id_libro=:b',{'b':row['id_libro']})

@app.before_request
def csrf():
    session.setdefault('csrf',secrets.token_hex(32))
    if request.method=='POST' and not secrets.compare_digest(request.form.get('csrf',''),session['csrf']):
        abort(400, description='Formulario vencido. Recarga la página.')

@app.context_processor
def context():
    return dict(models=MODELS,today=date.today().isoformat())

@app.errorhandler(oracledb.Error)
def oracle_error(error):
    logging.exception('Error de Oracle')
    code=getattr(error.args[0],'code',None)
    messages={1:'Ya existe un registro con ese carnet o esa devolución.',2292:'No se puede eliminar: el registro tiene préstamos u otras relaciones.',2291:'El registro relacionado no existe. Verifica el estudiante, libro o categoría.',942:'No se encuentran las tablas. Usa el mismo usuario y servicio donde ejecutaste tu script.'}
    return render_template('error.html',message=messages.get(code,'No se pudo completar la operación en Oracle. Revisa tu conexión y la consola.')),503

@app.errorhandler(ValueError)
def value_error(error):
    return render_template('error.html',message=str(error)),400

@app.after_request
def security_headers(resp):
    resp.headers['X-Content-Type-Options']='nosniff'
    resp.headers['X-Frame-Options']='DENY'
    resp.headers['Referrer-Policy']='same-origin'
    return resp

@app.route('/')
def home():
    with db() as con:
        stats={table:query(con,f'SELECT COUNT(*) n FROM {table}')[0]['n'] for table in ('libros','estudiantes','prestamos')}
        stats['disponibles']=query(con,'SELECT NVL(SUM(disponible),0) n FROM libros')[0]['n']
        stats['pendientes']=query(con,"SELECT COUNT(*) n FROM prestamos WHERE estado<>'Devuelto'")[0]['n']
        stats['atrasados']=query(con,"SELECT COUNT(*) n FROM prestamos WHERE estado<>'Devuelto' AND fecha_limite<TRUNC(SYSDATE)")[0]['n']
    return render_template('home.html',stats=stats)

@app.route('/catalogo/<table>')
def listing(table):
    if table not in MODELS: abort(404)
    label,pk,fields=MODELS[table]
    term=request.args.get('q','').strip()
    conditions=' OR '.join(f'LOWER({f[0]}) LIKE :q' for f in fields if f[2] in ('text','email'))
    with db() as con:
        rows=query(con,f'SELECT * FROM {table}'+(f' WHERE {conditions}' if term else '')+f' ORDER BY {pk} DESC',{'q':'%'+term.lower()+'%'} if term else {})
    return render_template('listing.html',table=table,label=label,pk=pk,fields=fields,rows=rows,term=term)

@app.route('/catalogo/<table>/editar',methods=['GET','POST'])
@app.route('/catalogo/<table>/editar/<int:ident>',methods=['GET','POST'])
def edit(table,ident=None):
    if table not in MODELS: abort(404)
    label,pk,fields=MODELS[table]
    with db() as con:
        rows=query(con,f'SELECT * FROM {table} WHERE {pk}=:i',{'i':ident}) if ident else []
        if ident and not rows: abort(404)
        row=rows[0] if rows else {}
        categories=query(con,'SELECT id_categoria,nombre_categoria FROM categorias ORDER BY nombre_categoria') if table=='libros' else []
        authors=query(con,"SELECT id_autor,nombre||' '||apellido nombre FROM autores ORDER BY nombre") if table=='libros' else []
        selected=[r['id_autor'] for r in query(con,'SELECT id_autor FROM libro_autor WHERE id_libro=:i',{'i':ident})] if table=='libros' and ident else []
        if request.method=='POST':
            data={}
            for name,title,kind,required,length in fields:
                value=request.form.get(name,'').strip()
                if required and not value: raise ValueError(f'{title} es obligatorio.')
                if kind in ('number','select') and value:
                    value=integer(value,title,1 if kind=='select' else 0)
                    if name=='publicacion' and not 1<=value<=9999: raise ValueError('Año inválido.')
                    if name=='disponible' and value>99999999: raise ValueError('Cantidad demasiado grande.')
                elif length and len(value)>length: raise ValueError(f'{title}: máximo {length} caracteres.')
                data[name]=value if value!='' else None
            if ident:
                data['i']=ident
                execute(con,f"UPDATE {table} SET "+','.join(f'{f[0]}=:{f[0]}' for f in fields)+f' WHERE {pk}=:i',data)
            else:
                # Los triggers del usuario generan las claves; RETURNING recupera la asignada.
                with con.cursor() as cur:
                    out=cur.var(oracledb.NUMBER)
                    cur.execute(f"INSERT INTO {table} ("+','.join(data)+') VALUES('+','.join(':'+k for k in data)+f') RETURNING {pk} INTO :out',dict(data,out=out))
                    ident=int(out.getvalue()[0])
            if table=='libros':
                execute(con,'DELETE FROM libro_autor WHERE id_libro=:i',{'i':ident})
                for author in set(request.form.getlist('autores')):
                    execute(con,'INSERT INTO libro_autor(id_libro,id_autor) VALUES(:i,:a)',{'i':ident,'a':integer(author,'Autor',1)})
            flash('Registro guardado correctamente.')
            return redirect(url_for('listing',table=table))
    return render_template('edit.html',table=table,label=label,fields=fields,row=row,categories=categories,authors=authors,selected=selected)

@app.post('/catalogo/<table>/eliminar/<int:ident>')
def delete(table,ident):
    if table not in MODELS: abort(404)
    with db() as con:
        if table=='libros': execute(con,'DELETE FROM libro_autor WHERE id_libro=:i',{'i':ident})
        if table=='autores': execute(con,'DELETE FROM libro_autor WHERE id_autor=:i',{'i':ident})
        execute(con,f'DELETE FROM {table} WHERE {MODELS[table][1]}=:i',{'i':ident})
    flash('Registro eliminado.')
    return redirect(url_for('listing',table=table))

LOAN_SQL="""SELECT p.id_prestamo,e.carnet,e.nombre||' '||e.apellido estudiante,l.titulo,
p.fecha_prestamo,p.fecha_limite,
CASE WHEN p.estado='Devuelto' THEN 'Devuelto' WHEN p.fecha_limite<TRUNC(SYSDATE) THEN 'Atrasado' ELSE p.estado END estado,
d.fecha_devolucion,d.monto_multa,d.observaciones
FROM prestamos p JOIN estudiantes e ON e.id_estudiante=p.id_estudiante
JOIN libros l ON l.id_libro=p.id_libro LEFT JOIN devoluciones d ON d.id_prestamo=p.id_prestamo"""

def loan_rows(con):
    clauses=[]; params={}
    term=request.args.get('q','').strip()
    if term:
        clauses.append("(LOWER(l.titulo) LIKE :q OR LOWER(e.carnet) LIKE :q OR LOWER(e.nombre||' '||e.apellido) LIKE :q)")
        params['q']='%'+term.lower()+'%'
    state=request.args.get('estado','')
    if state=='Devuelto': clauses.append("p.estado='Devuelto'")
    elif state=='Atrasado': clauses.append("p.estado<>'Devuelto' AND p.fecha_limite<TRUNC(SYSDATE)")
    elif state=='Activo': clauses.append("p.estado<>'Devuelto' AND (p.fecha_limite>=TRUNC(SYSDATE) OR p.fecha_limite IS NULL)")
    for key,op in [('desde','>='),('hasta','<=')]:
        if request.args.get(key):
            clauses.append(f'TRUNC(p.fecha_prestamo){op}:{key}')
            params[key]=parsedate(request.args[key])
    if 'desde' in params and 'hasta' in params and params['desde']>params['hasta']: raise ValueError('Rango de fechas inválido.')
    return query(con,LOAN_SQL+(' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY p.id_prestamo DESC',params)

@app.get('/prestamos')
def loans():
    with db() as con: rows=loan_rows(con)
    return render_template('loans.html',rows=rows)

@app.route('/prestamos/nuevo',methods=['GET','POST'])
def loan_create():
    with db() as con:
        if request.method=='POST':
            new_loan(con,integer(request.form.get('estudiante'),'Estudiante',1),integer(request.form.get('libro'),'Libro',1),parsedate(request.form.get('fecha')),parsedate(request.form.get('limite')))
            flash('Préstamo registrado. Existencias actualizadas.')
            return redirect(url_for('loans'))
        students=query(con,"SELECT id_estudiante,carnet||' · '||nombre||' '||apellido nombre FROM estudiantes ORDER BY nombre")
        books=query(con,'SELECT id_libro,titulo,disponible FROM libros WHERE disponible>0 ORDER BY titulo')
    return render_template('loan_new.html',students=students,books=books)

@app.route('/devolver/<int:ident>',methods=['GET','POST'])
def return_create(ident):
    with db() as con:
        if request.method=='POST':
            try: fine=Decimal(request.form.get('multa','0'))
            except InvalidOperation: raise ValueError('Multa inválida.')
            if not fine.is_finite() or fine<0 or fine>Decimal('9999.99') or fine!=fine.quantize(Decimal('.01')): raise ValueError('Multa: de 0 a 9999.99 con máximo dos decimales.')
            notes=request.form.get('observaciones','').strip()
            if len(notes)>200: raise ValueError('Observaciones: máximo 200 caracteres.')
            return_loan(con,ident,parsedate(request.form.get('fecha')),notes,fine)
            flash('Devolución registrada. Ejemplar disponible nuevamente.')
            return redirect(url_for('loans'))
        rows=query(con,LOAN_SQL+' WHERE p.id_prestamo=:i',{'i':ident})
        if not rows: abort(404)
        if rows[0]['estado']=='Devuelto': raise ValueError('Este préstamo ya fue devuelto.')
    return render_template('return.html',row=rows[0])

@app.get('/reportes/csv')
def export():
    with db() as con: rows=loan_rows(con)
    stream=io.StringIO(); writer=csv.writer(stream,delimiter=';')
    keys=['id_prestamo','carnet','estudiante','titulo','fecha_prestamo','fecha_limite','estado','fecha_devolucion','monto_multa','observaciones']
    writer.writerow(keys)
    for row in rows:
        values=[]
        for key in keys:
            value=row[key]
            if isinstance(value,datetime): value=value.strftime('%Y-%m-%d')
            value='' if value is None else str(value)
            if value.startswith(('=','+','-','@','\t','\r','\n')): value="'"+value
            values.append(value)
        writer.writerow(values)
    return Response('\ufeff'+stream.getvalue(),mimetype='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename=prestamos_biblioteca.csv'})

if __name__=='__main__':
    from waitress import serve
    print('Biblioteca disponible en http://127.0.0.1:5000')
    serve(app,host='127.0.0.1',port=5000)
