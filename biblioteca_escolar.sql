/*MÓDULO 1: CATÁLOGO DE LIBROS*/

/*Tabla CATEGORIAS*/
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

/*Tabla AUTORES*/
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

/*Tabla LIBROS*/
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

/*Tabla LIBRO_AUTOR (relación muchos a muchos entre Libros y Autores)*/
CREATE TABLE libro_autor (
    id_libro  NUMBER NOT NULL,
    id_autor  NUMBER NOT NULL,
    CONSTRAINT pk_libro_autor PRIMARY KEY (id_libro, id_autor),
    CONSTRAINT fk_libroautor_libro FOREIGN KEY (id_libro)
        REFERENCES libros(id_libro),
    CONSTRAINT fk_libroautor_autor FOREIGN KEY (id_autor)
        REFERENCES autores(id_autor)
);

/*MÓDULO 2: ESTUDIANTES*/

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

/*MÓDULO 3: TRANSACCIONES (PRÉSTAMOS Y DEVOLUCIONES)*/

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

/*DATOS DE EJEMPLO*/

/*Categorías*/
INSERT INTO categorias (nombre_categoria, descripcion) VALUES ('Matemática', 'Libros de álgebra, geometría y cálculo');
INSERT INTO categorias (nombre_categoria, descripcion) VALUES ('Ciencias Sociales', 'Historia, geografía y cívica');
INSERT INTO categorias (nombre_categoria, descripcion) VALUES ('Literatura', 'Novelas y obras literarias clásicas y contemporáneas');
INSERT INTO categorias (nombre_categoria, descripcion) VALUES ('Ciencias Naturales', 'Biología, física y química');

/*Autores*/
INSERT INTO autores (nombre, apellido, nacionalidad) VALUES ('Gabriel', 'García Márquez', 'Colombiana');
INSERT INTO autores (nombre, apellido, nacionalidad) VALUES ('Miguel', 'de Cervantes', 'Española');
INSERT INTO autores (nombre, apellido, nacionalidad) VALUES ('Isaac', 'Asimov', 'Estadounidense');
INSERT INTO autores (nombre, apellido, nacionalidad) VALUES ('Mario', 'Vargas Llosa', 'Peruana');

/*Libros*/
INSERT INTO libros (titulo, isbn, publicacion, disponible, id_categoria)
VALUES ('Cien Años de Soledad', '978-0307474728', 1967, 3, 3);
INSERT INTO libros (titulo, isbn, publicacion, disponible, id_categoria)
VALUES ('Don Quijote de la Mancha', '978-8420412146', 1605, 2, 3);
INSERT INTO libros (titulo, isbn, publicacion, disponible, id_categoria)
VALUES ('Fundación', '978-8497593558', 1951, 4, 4);
INSERT INTO libros (titulo, isbn, publicacion, disponible, id_categoria)
VALUES ('La Ciudad y los Perros', '978-8420471860', 1963, 2, 3);

/*Libro-Autor*/
INSERT INTO libro_autor (id_libro, id_autor) VALUES (1, 1);
INSERT INTO libro_autor (id_libro, id_autor) VALUES (2, 2);
INSERT INTO libro_autor (id_libro, id_autor) VALUES (3, 3);
INSERT INTO libro_autor (id_libro, id_autor) VALUES (4, 4);

/*Estudiantes*/
INSERT INTO estudiantes (carnet, nombre, apellido, grado_seccion, correo)
VALUES ('1190-24-13377', 'Henry Alejandro', 'Bardales Aguilar', 'Quinto Bachillerato - A', 'hbardales@miumg.edu.gt');
INSERT INTO estudiantes (carnet, nombre, apellido, grado_seccion, correo)
VALUES ('1190-24-7563', 'Oscar Eduardo', 'Urzúa Mejía', 'Quinto Bachillerato - A', 'ourzua@miumg.edu.gt');
INSERT INTO estudiantes (carnet, nombre, apellido, grado_seccion, correo)
VALUES ('1190-24-3065', 'Jhonatan Estuardo', 'García López', 'Quinto Bachillerato - B', 'jgarcia@miumg.edu.gt');

/*Préstamos*/
INSERT INTO prestamos (id_estudiante, id_libro, fecha_prestamo, fecha_limite, estado)
VALUES (1, 1, DATE '2026-10-01', DATE '2026-10-08', 'Activo');
INSERT INTO prestamos (id_estudiante, id_libro, fecha_prestamo, fecha_limite, estado)
VALUES (2, 3, DATE '2026-09-20', DATE '2026-09-27', 'Devuelto');
INSERT INTO prestamos (id_estudiante, id_libro, fecha_prestamo, fecha_limite, estado)
VALUES (3, 2, DATE '2026-09-15', DATE '2026-09-22', 'Atrasado');

/*Devoluciones (solo del préstamo ya devuelto)*/
INSERT INTO devoluciones (id_prestamo, fecha_devolucion, observaciones, monto_multa)
VALUES (2, DATE '2026-09-26', 'Entregado a tiempo, buen estado', 0);

COMMIT;

/*CONSULTAS DE VERIFICACIÓN*/

/*Ver todos los libros con su categoría*/
SELECT l.titulo, l.isbn, c.nombre_categoria, l.disponible
FROM libros l
JOIN categorias c ON l.id_categoria = c.id_categoria;

/*Ver préstamos activos con datos del estudiante y del libro*/
SELECT p.id_prestamo, e.nombre || ' ' || e.apellido AS estudiante,
       li.titulo, p.fecha_prestamo, p.fecha_limite, p.estado
FROM prestamos p
JOIN estudiantes e ON p.id_estudiante = e.id_estudiante
JOIN libros li ON p.id_libro = li.id_libro
WHERE p.estado = 'Activo';

/*Ver libros con sus autores*/
SELECT li.titulo, a.nombre || ' ' || a.apellido AS autor
FROM libros li
JOIN libro_autor la ON li.id_libro = la.id_libro
JOIN autores a ON la.id_autor = a.id_autor;