CREATE TABLE categorias (
    id_categoria      NUMBER PRIMARY KEY,
    nombre_categoria  VARCHAR2(50) NOT NULL,
    descripcion       VARCHAR2(200)
);

CREATE SEQUENCE seq_categorias START WITH 1 INCREMENT BY 1;

CREATE OR REPLACE TRIGGER trg_categorias
BEFORE INSERT ON categorias
FOR EACH ROW
BEGIN
    IF :NEW.id_categoria IS NULL THEN
        :NEW.id_categoria := seq_categorias.NEXTVAL;
    END IF;
END;
/

CREATE TABLE autores (
    id_autor      NUMBER PRIMARY KEY,
    nombre        VARCHAR2(50) NOT NULL,
    apellido      VARCHAR2(50) NOT NULL,
    nacionalidad  VARCHAR2(50)
);

CREATE SEQUENCE seq_autores START WITH 1 INCREMENT BY 1;

CREATE OR REPLACE TRIGGER trg_autores
BEFORE INSERT ON autores
FOR EACH ROW
BEGIN
    IF :NEW.id_autor IS NULL THEN
        :NEW.id_autor := seq_autores.NEXTVAL;
    END IF;
END;
/

CREATE TABLE libros (
    id_libro      NUMBER PRIMARY KEY,
    titulo        VARCHAR2(150) NOT NULL,
    isbn          VARCHAR2(20),
    publicacion   NUMBER(4),
    disponible    NUMBER DEFAULT 0,
    id_categoria  NUMBER NOT NULL,
    CONSTRAINT fk_libros_categoria FOREIGN KEY (id_categoria)
        REFERENCES categorias(id_categoria)
);

CREATE SEQUENCE seq_libros START WITH 1 INCREMENT BY 1;

CREATE OR REPLACE TRIGGER trg_libros
BEFORE INSERT ON libros
FOR EACH ROW
BEGIN
    IF :NEW.id_libro IS NULL THEN
        :NEW.id_libro := seq_libros.NEXTVAL;
    END IF;
END;
/

CREATE TABLE libro_autor (
    id_libro  NUMBER NOT NULL,
    id_autor  NUMBER NOT NULL,
    CONSTRAINT pk_libro_autor PRIMARY KEY (id_libro, id_autor),
    CONSTRAINT fk_libroautor_libro FOREIGN KEY (id_libro)
        REFERENCES libros(id_libro),
    CONSTRAINT fk_libroautor_autor FOREIGN KEY (id_autor)
        REFERENCES autores(id_autor)
);

CREATE TABLE estudiantes (
    id_estudiante  NUMBER PRIMARY KEY,
    carnet         VARCHAR2(20) NOT NULL UNIQUE,
    nombre         VARCHAR2(50) NOT NULL,
    apellido       VARCHAR2(50) NOT NULL,
    grado_seccion  VARCHAR2(30),
    correo         VARCHAR2(100)
);

CREATE SEQUENCE seq_estudiantes START WITH 1 INCREMENT BY 1;

CREATE OR REPLACE TRIGGER trg_estudiantes
BEFORE INSERT ON estudiantes
FOR EACH ROW
BEGIN
    IF :NEW.id_estudiante IS NULL THEN
        :NEW.id_estudiante := seq_estudiantes.NEXTVAL;
    END IF;
END;
/

CREATE TABLE usuarios (
    id_usuario      NUMBER PRIMARY KEY,
    usuario         VARCHAR2(50) NOT NULL UNIQUE,
    clave_hash      VARCHAR2(255) NOT NULL,
    nombre_completo VARCHAR2(100) NOT NULL,
    rol             VARCHAR2(20) DEFAULT 'ESTUDIANTE' NOT NULL,
    id_estudiante   NUMBER,
    fecha_creacion  DATE DEFAULT SYSDATE,
    CONSTRAINT fk_usuarios_estudiante FOREIGN KEY (id_estudiante)
        REFERENCES estudiantes(id_estudiante),
    CONSTRAINT chk_usuarios_rol CHECK (rol IN ('ADMIN', 'ESTUDIANTE'))
);

CREATE SEQUENCE seq_usuarios START WITH 1 INCREMENT BY 1;

CREATE OR REPLACE TRIGGER trg_usuarios
BEFORE INSERT ON usuarios
FOR EACH ROW
BEGIN
    IF :NEW.id_usuario IS NULL THEN
        :NEW.id_usuario := seq_usuarios.NEXTVAL;
    END IF;
END;
/

CREATE TABLE prestamos (
    id_prestamo     NUMBER PRIMARY KEY,
    id_estudiante   NUMBER NOT NULL,
    id_libro        NUMBER NOT NULL,
    fecha_prestamo  DATE DEFAULT SYSDATE,
    fecha_limite    DATE,
    estado          VARCHAR2(20) DEFAULT 'Activo',
    CONSTRAINT fk_prestamos_estudiante FOREIGN KEY (id_estudiante)
        REFERENCES estudiantes(id_estudiante),
    CONSTRAINT fk_prestamos_libro FOREIGN KEY (id_libro)
        REFERENCES libros(id_libro),
    CONSTRAINT chk_prestamos_estado CHECK (estado IN ('Activo', 'Devuelto', 'Atrasado'))
);

CREATE SEQUENCE seq_prestamos START WITH 1 INCREMENT BY 1;

CREATE OR REPLACE TRIGGER trg_prestamos
BEFORE INSERT ON prestamos
FOR EACH ROW
BEGIN
    IF :NEW.id_prestamo IS NULL THEN
        :NEW.id_prestamo := seq_prestamos.NEXTVAL;
    END IF;
END;
/

CREATE TABLE devoluciones (
    id_devolucion     NUMBER PRIMARY KEY,
    id_prestamo       NUMBER NOT NULL UNIQUE,
    fecha_devolucion  DATE DEFAULT SYSDATE,
    observaciones     VARCHAR2(200),
    monto_multa       NUMBER(6,2) DEFAULT 0,
    CONSTRAINT fk_devoluciones_prestamo FOREIGN KEY (id_prestamo)
        REFERENCES prestamos(id_prestamo)
);

CREATE SEQUENCE seq_devoluciones START WITH 1 INCREMENT BY 1;

CREATE OR REPLACE TRIGGER trg_devoluciones
BEFORE INSERT ON devoluciones
FOR EACH ROW
BEGIN
    IF :NEW.id_devolucion IS NULL THEN
        :NEW.id_devolucion := seq_devoluciones.NEXTVAL;
    END IF;
END;
/

CREATE TABLE reservas (
    id_reserva      NUMBER PRIMARY KEY,
    id_estudiante   NUMBER NOT NULL,
    id_libro        NUMBER NOT NULL,
    fecha_reserva   DATE DEFAULT SYSDATE,
    estado          VARCHAR2(20) DEFAULT 'Pendiente',
    CONSTRAINT fk_reservas_estudiante FOREIGN KEY (id_estudiante)
        REFERENCES estudiantes(id_estudiante),
    CONSTRAINT fk_reservas_libro FOREIGN KEY (id_libro)
        REFERENCES libros(id_libro),
    CONSTRAINT chk_reservas_estado CHECK (estado IN ('Pendiente', 'Atendida', 'Cancelada'))
);

CREATE SEQUENCE seq_reservas START WITH 1 INCREMENT BY 1;

CREATE OR REPLACE TRIGGER trg_reservas
BEFORE INSERT ON reservas
FOR EACH ROW
BEGIN
    IF :NEW.id_reserva IS NULL THEN
        :NEW.id_reserva := seq_reservas.NEXTVAL;
    END IF;
END;
/

CREATE TABLE auditoria (
    id_auditoria    NUMBER PRIMARY KEY,
    tabla_afectada  VARCHAR2(30) NOT NULL,
    operacion       VARCHAR2(20) NOT NULL,
    id_registro     NUMBER,
    detalles        VARCHAR2(255),
    fecha_hora      DATE DEFAULT SYSDATE,
    usuario         VARCHAR2(50) DEFAULT 'SISTEMA'
);

CREATE SEQUENCE seq_auditoria START WITH 1 INCREMENT BY 1;

CREATE OR REPLACE TRIGGER trg_auditoria
BEFORE INSERT ON auditoria
FOR EACH ROW
BEGIN
    IF :NEW.id_auditoria IS NULL THEN
        :NEW.id_auditoria := seq_auditoria.NEXTVAL;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER trg_audit_prestamos
AFTER INSERT OR UPDATE ON prestamos
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO auditoria (tabla_afectada, operacion, id_registro, detalles)
        VALUES ('PRESTAMOS', 'INSERT', :NEW.id_prestamo, 'Nuevo prestamo a estudiante ID ' || :NEW.id_estudiante || ' libro ID ' || :NEW.id_libro);
    ELSIF UPDATING THEN
        INSERT INTO auditoria (tabla_afectada, operacion, id_registro, detalles)
        VALUES ('PRESTAMOS', 'UPDATE', :NEW.id_prestamo, 'Estado cambio de ' || :OLD.estado || ' a ' || :NEW.estado);
    END IF;
END;
/

CREATE OR REPLACE TRIGGER trg_audit_devoluciones
AFTER INSERT ON devoluciones
FOR EACH ROW
BEGIN
    INSERT INTO auditoria (tabla_afectada, operacion, id_registro, detalles)
    VALUES ('DEVOLUCIONES', 'INSERT', :NEW.id_devolucion, 'Devolucion prestamo ID ' || :NEW.id_prestamo || ' multa ' || :NEW.monto_multa);
END;
/

CREATE INDEX idx_prestamos_estudiante ON prestamos(id_estudiante);
CREATE INDEX idx_prestamos_libro ON prestamos(id_libro);
CREATE INDEX idx_prestamos_estado ON prestamos(estado);
CREATE INDEX idx_libros_categoria ON libros(id_categoria);
CREATE INDEX idx_estudiantes_carnet ON estudiantes(carnet);
CREATE INDEX idx_reservas_estudiante ON reservas(id_estudiante);
CREATE INDEX idx_reservas_libro ON reservas(id_libro);
CREATE INDEX idx_usuarios_usuario ON usuarios(usuario);

CREATE OR REPLACE VIEW v_prestamos_detalle AS
SELECT p.id_prestamo,
       e.id_estudiante,
       e.carnet,
       e.nombre || ' ' || e.apellido AS estudiante,
       e.correo,
       l.id_libro,
       l.titulo,
       l.isbn,
       p.fecha_prestamo,
       p.fecha_limite,
       CASE 
           WHEN p.estado = 'Devuelto' THEN 'Devuelto'
           WHEN p.fecha_limite < TRUNC(SYSDATE) THEN 'Atrasado'
           ELSE p.estado 
       END AS estado,
       d.id_devolucion,
       d.fecha_devolucion,
       d.monto_multa,
       d.observaciones
FROM prestamos p
JOIN estudiantes e ON e.id_estudiante = p.id_estudiante
JOIN libros l ON l.id_libro = p.id_libro
LEFT JOIN devoluciones d ON d.id_prestamo = p.id_prestamo;

CREATE OR REPLACE VIEW v_estadisticas_dashboard AS
SELECT 
    (SELECT COUNT(*) FROM libros) AS total_titulos,
    (SELECT NVL(SUM(disponible), 0) FROM libros) AS total_disponibles,
    (SELECT COUNT(*) FROM estudiantes) AS total_estudiantes,
    (SELECT COUNT(*) FROM prestamos WHERE estado <> 'Devuelto') AS prestamos_pendientes,
    (SELECT COUNT(*) FROM prestamos WHERE estado <> 'Devuelto' AND fecha_limite < TRUNC(SYSDATE)) AS prestamos_atrasados,
    (SELECT COUNT(*) FROM prestamos) AS prestamos_historicos,
    (SELECT COUNT(*) FROM reservas WHERE estado = 'Pendiente') AS reservas_pendientes
FROM DUAL;

CREATE OR REPLACE VIEW v_top_libros AS
SELECT l.id_libro, l.titulo, COUNT(p.id_prestamo) AS total_prestamos
FROM libros l
LEFT JOIN prestamos p ON l.id_libro = p.id_libro
GROUP BY l.id_libro, l.titulo
ORDER BY total_prestamos DESC;

CREATE MATERIALIZED VIEW mv_resumen_categorias
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT c.id_categoria,
       c.nombre_categoria,
       COUNT(l.id_libro) AS total_libros,
       NVL(SUM(l.disponible), 0) AS total_disponibles
FROM categorias c
LEFT JOIN libros l ON c.id_categoria = l.id_categoria
GROUP BY c.id_categoria, c.nombre_categoria;

CREATE OR REPLACE PROCEDURE sp_registrar_prestamo (
    p_id_estudiante  IN NUMBER,
    p_id_libro       IN NUMBER,
    p_fecha_prestamo IN DATE,
    p_fecha_limite   IN DATE
) AS
    v_disponible     NUMBER;
    v_activos        NUMBER;
    v_atrasados      NUMBER;
    v_estado_inicial VARCHAR2(20);
BEGIN
    IF p_fecha_limite < p_fecha_prestamo THEN
        RAISE_APPLICATION_ERROR(-20001, 'La fecha limite no puede ser anterior al prestamo.');
    END IF;
    IF p_fecha_prestamo > TRUNC(SYSDATE) THEN
        RAISE_APPLICATION_ERROR(-20002, 'El prestamo no puede tener fecha futura.');
    END IF;

    SELECT COUNT(*) INTO v_atrasados
    FROM prestamos
    WHERE id_estudiante = p_id_estudiante
      AND estado <> 'Devuelto'
      AND fecha_limite < TRUNC(SYSDATE);

    IF v_atrasados > 0 THEN
        RAISE_APPLICATION_ERROR(-20003, 'El estudiante tiene prestamos atrasados pendientes.');
    END IF;

    SELECT COUNT(*) INTO v_activos
    FROM prestamos
    WHERE id_estudiante = p_id_estudiante
      AND estado <> 'Devuelto';

    IF v_activos >= 3 THEN
        RAISE_APPLICATION_ERROR(-20004, 'El estudiante ya tiene el maximo de 3 prestamos activos permitidos.');
    END IF;

    SELECT disponible INTO v_disponible
    FROM libros
    WHERE id_libro = p_id_libro
    FOR UPDATE;

    IF v_disponible < 1 THEN
        RAISE_APPLICATION_ERROR(-20005, 'El libro no tiene ejemplares disponibles.');
    END IF;

    UPDATE libros
    SET disponible = disponible - 1
    WHERE id_libro = p_id_libro;

    IF p_fecha_limite < TRUNC(SYSDATE) THEN
        v_estado_inicial := 'Atrasado';
    ELSE
        v_estado_inicial := 'Activo';
    END IF;

    INSERT INTO prestamos (id_estudiante, id_libro, fecha_prestamo, fecha_limite, estado)
    VALUES (p_id_estudiante, p_id_libro, p_fecha_prestamo, p_fecha_limite, v_estado_inicial);
END;
/

CREATE OR REPLACE PROCEDURE sp_registrar_devolucion (
    p_id_prestamo      IN NUMBER,
    p_fecha_devolucion IN DATE,
    p_observaciones    IN VARCHAR2,
    p_multa_dano       IN NUMBER
) AS
    v_id_libro        NUMBER;
    v_fecha_prestamo  DATE;
    v_fecha_limite    DATE;
    v_estado          VARCHAR2(20);
    v_dias_retraso    NUMBER;
    v_multa_total     NUMBER;
    v_ya_devuelto     NUMBER;
BEGIN
    SELECT id_libro, fecha_prestamo, fecha_limite, estado
    INTO v_id_libro, v_fecha_prestamo, v_fecha_limite, v_estado
    FROM prestamos
    WHERE id_prestamo = p_id_prestamo
    FOR UPDATE;

    SELECT COUNT(*) INTO v_ya_devuelto
    FROM devoluciones
    WHERE id_prestamo = p_id_prestamo;

    IF v_estado = 'Devuelto' OR v_ya_devuelto > 0 THEN
        RAISE_APPLICATION_ERROR(-20010, 'Este prestamo ya fue devuelto.');
    END IF;

    IF p_fecha_devolucion < TRUNC(v_fecha_prestamo) OR p_fecha_devolucion > TRUNC(SYSDATE) THEN
        RAISE_APPLICATION_ERROR(-20011, 'La devolucion debe estar entre la fecha del prestamo y hoy.');
    END IF;

    IF v_fecha_limite IS NOT NULL AND p_fecha_devolucion > TRUNC(v_fecha_limite) THEN
        v_dias_retraso := TRUNC(p_fecha_devolucion) - TRUNC(v_fecha_limite);
    ELSE
        v_dias_retraso := 0;
    END IF;

    v_multa_total := (v_dias_retraso * 5.00) + NVL(p_multa_dano, 0);

    INSERT INTO devoluciones (id_prestamo, fecha_devolucion, observaciones, monto_multa)
    VALUES (p_id_prestamo, p_fecha_devolucion, p_observaciones, v_multa_total);

    UPDATE prestamos
    SET estado = 'Devuelto'
    WHERE id_prestamo = p_id_prestamo;

    UPDATE libros
    SET disponible = NVL(disponible, 0) + 1
    WHERE id_libro = v_id_libro;
END;
/

CREATE OR REPLACE PROCEDURE sp_renovar_prestamo (
    p_id_prestamo      IN NUMBER,
    p_dias_adicionales IN NUMBER DEFAULT 7
) AS
    v_estado       VARCHAR2(20);
    v_fecha_limite DATE;
BEGIN
    SELECT estado, fecha_limite
    INTO v_estado, v_fecha_limite
    FROM prestamos
    WHERE id_prestamo = p_id_prestamo
    FOR UPDATE;

    IF v_estado = 'Devuelto' THEN
        RAISE_APPLICATION_ERROR(-20020, 'No se puede renovar un prestamo ya devuelto.');
    END IF;

    IF v_fecha_limite < TRUNC(SYSDATE) THEN
        RAISE_APPLICATION_ERROR(-20021, 'No se puede renovar un prestamo que ya esta atrasado.');
    END IF;

    UPDATE prestamos
    SET fecha_limite = fecha_limite + p_dias_adicionales
    WHERE id_prestamo = p_id_prestamo;

    INSERT INTO auditoria (tabla_afectada, operacion, id_registro, detalles)
    VALUES ('PRESTAMOS', 'RENOVACION', p_id_prestamo, 'Prestamo renovado por ' || p_dias_adicionales || ' dias adicionales');
END;
/

INSERT INTO categorias (nombre_categoria, descripcion) VALUES ('Matemática', 'Libros de álgebra, geometría y cálculo');
INSERT INTO categorias (nombre_categoria, descripcion) VALUES ('Ciencias Sociales', 'Historia, geografía y cívica');
INSERT INTO categorias (nombre_categoria, descripcion) VALUES ('Literatura', 'Novelas y obras literarias clásicas y contemporáneas');
INSERT INTO categorias (nombre_categoria, descripcion) VALUES ('Ciencias Naturales', 'Biología, física y química');

INSERT INTO autores (nombre, apellido, nacionalidad) VALUES ('Gabriel', 'García Márquez', 'Colombiana');
INSERT INTO autores (nombre, apellido, nacionalidad) VALUES ('Miguel', 'de Cervantes', 'Española');
INSERT INTO autores (nombre, apellido, nacionalidad) VALUES ('Isaac', 'Asimov', 'Estadounidense');
INSERT INTO autores (nombre, apellido, nacionalidad) VALUES ('Mario', 'Vargas Llosa', 'Peruana');

INSERT INTO libros (titulo, isbn, publicacion, disponible, id_categoria)
VALUES ('Cien Años de Soledad', '978-0307474728', 1967, 3, 3);
INSERT INTO libros (titulo, isbn, publicacion, disponible, id_categoria)
VALUES ('Don Quijote de la Mancha', '978-8420412146', 1605, 2, 3);
INSERT INTO libros (titulo, isbn, publicacion, disponible, id_categoria)
VALUES ('Fundación', '978-8497593558', 1951, 4, 4);
INSERT INTO libros (titulo, isbn, publicacion, disponible, id_categoria)
VALUES ('La Ciudad y los Perros', '978-8420471860', 1963, 2, 3);

INSERT INTO libro_autor (id_libro, id_autor) VALUES (1, 1);
INSERT INTO libro_autor (id_libro, id_autor) VALUES (2, 2);
INSERT INTO libro_autor (id_libro, id_autor) VALUES (3, 3);
INSERT INTO libro_autor (id_libro, id_autor) VALUES (4, 4);

INSERT INTO estudiantes (carnet, nombre, apellido, grado_seccion, correo)
VALUES ('1190-24-1001', 'Juan', 'Pérez', 'Quinto Bachillerato - A', 'jperez@miumg.edu.gt');
INSERT INTO estudiantes (carnet, nombre, apellido, grado_seccion, correo)
VALUES ('1190-24-1002', 'María', 'López', 'Quinto Bachillerato - A', 'mlopez@miumg.edu.gt');
INSERT INTO estudiantes (carnet, nombre, apellido, grado_seccion, correo)
VALUES ('1190-24-1003', 'Carlos', 'Gómez', 'Quinto Bachillerato - B', 'cgomez@miumg.edu.gt');

INSERT INTO usuarios (usuario, clave_hash, nombre_completo, rol, id_estudiante)
VALUES ('admin', 'scrypt:32768:8:1$Wou1cFDkbt0AKlCj$8d39f5de61b153f89b5e76cb791406a503260320f88e9ddf89a390832d0d60d6e538868c6f506534e22b81a2ff4e19c3453cdedeedc66bbc7398198691627ab0', 'Administrador General', 'ADMIN', NULL);

INSERT INTO usuarios (usuario, clave_hash, nombre_completo, rol, id_estudiante)
VALUES ('estudiante', 'scrypt:32768:8:1$9xiPoqINpbIZLIIB$fdaf194af0456e6611894d683488df6003c3de4eb9c839b494df886256cb795a434270578d9a9aa1c8d57ef097e29bfb5366c56f7cb6ae797f1d61b4fc0dd921', 'Juan Pérez Demo', 'ESTUDIANTE', 1);

INSERT INTO prestamos (id_estudiante, id_libro, fecha_prestamo, fecha_limite, estado)
VALUES (1, 1, DATE '2026-10-01', DATE '2026-10-08', 'Activo');
INSERT INTO prestamos (id_estudiante, id_libro, fecha_prestamo, fecha_limite, estado)
VALUES (2, 3, DATE '2026-09-20', DATE '2026-09-27', 'Devuelto');
INSERT INTO prestamos (id_estudiante, id_libro, fecha_prestamo, fecha_limite, estado)
VALUES (3, 2, DATE '2026-09-15', DATE '2026-09-22', 'Atrasado');

INSERT INTO devoluciones (id_prestamo, fecha_devolucion, observaciones, monto_multa)
VALUES (2, DATE '2026-09-26', 'Entregado a tiempo, buen estado', 0);

INSERT INTO reservas (id_estudiante, id_libro, fecha_reserva, estado)
VALUES (1, 2, DATE '2026-10-02', 'Pendiente');

COMMIT;

SELECT p.id_prestamo AS id_registro,
       e.carnet,
       e.nombre || ' ' || e.apellido AS estudiante,
       l.titulo AS libro,
       p.fecha_prestamo AS fecha,
       p.estado AS estado,
       'PRESTAMO' AS tipo
FROM prestamos p
JOIN estudiantes e ON e.id_estudiante = p.id_estudiante
JOIN libros l ON l.id_libro = p.id_libro
UNION
SELECT r.id_reserva AS id_registro,
       e.carnet,
       e.nombre || ' ' || e.apellido AS estudiante,
       l.titulo AS libro,
       r.fecha_reserva AS fecha,
       r.estado AS estado,
       'RESERVA' AS tipo
FROM reservas r
JOIN estudiantes e ON e.id_estudiante = r.id_estudiante
JOIN libros l ON l.id_libro = r.id_libro;

