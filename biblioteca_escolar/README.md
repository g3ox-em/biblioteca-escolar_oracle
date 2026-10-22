# Sistema de Biblioteca Escolar — Oracle + Python
Proyecto local para Bases de Datos I, Universidad Mariano Gálvez de Guatemala.

## 1. Requisitos
- Windows con Python 3.11 o posterior (marca «Add Python to PATH» al instalar).
- Oracle funcionando y las siete tablas, secuencias y triggers del script original ya creados.
- Visual Studio Code, opcional.
- Internet para la primera instalación de dependencias.

SQL Developer es el cliente para administrar Oracle. El sistema se conecta al servidor Oracle; SQL Developer puede estar cerrado.

## 2. Configurar la misma conexión
Descomprime el ZIP y abre la carpeta biblioteca_escolar. Copia `.env.example` y nombra la copia `.env` (sin `.txt`).
Edita:
```
DB_USER=usuario_que_tiene_las_tablas
DB_PASSWORD=tu_contrasena
DB_DSN=localhost:1521/XEPDB1
```
En SQL Developer, clic derecho sobre tu conexión > Propiedades. Copia el usuario, hostname, puerto y **nombre del servicio**. DB_DSN tiene formato `HOST:PUERTO/SERVICIO`. XEPDB1 es solo un ejemplo: puede ser FREEPDB1 u otro valor.
Si SQL Developer tiene seleccionado **SID**, usa DB_SID, DB_HOST y DB_PORT en lugar del servicio. No confundas el nombre visible de la conexión con el servicio. Usa el mismo usuario/esquema; no SYSTEM si las tablas están en otro usuario. No compartas .env.

## 3. Iniciar
Doble clic en `iniciar.bat`. Primero crea el entorno y descarga los paquetes. Cuando aparezca la dirección, abre http://127.0.0.1:5000 en tu navegador. Mantén la ventana de consola abierta. Ctrl+C detiene el sistema.

Alternativa en la terminal de VS Code:
```
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

## 4. Funciones
- Panel: títulos, estudiantes, ejemplares, pendientes y vencidos.
- Crear, buscar, editar y eliminar categorías, autores, libros y estudiantes.
- Asignar varios autores a un libro desde casillas.
- Registrar préstamos y descontar un ejemplar; rechazar saldo insuficiente.
- Registrar devoluciones con multa manual y observaciones; aumentar saldo.
- Bloqueos transaccionales para evitar doble devolución y saldo negativo por concurrencia.
- Historial con filtros de carnet, nombre, título, estado y rango de fecha de préstamo.
- CSV UTF-8 con separador punto y coma para Excel. Si Excel no separa columnas, usa Datos > Desde texto/CSV > separador punto y coma.
- Imprimir o guardar PDF con el diálogo del navegador (para tablas anchas, orientación horizontal).
- Confirmación antes de prestar, devolver o eliminar. Las relaciones de Oracle impiden eliminar registros usados en préstamos.
- Diseño adaptable a celular, tablet y navegador.

## 5. Revisar los datos iniciales (importante)
`libros.disponible` representa **ejemplares disponibles ahora**, no el total adquirido. Tu script inserta préstamos, pero no descuenta ese saldo.
Antes de trabajar, confirma si 3, 2, 4 y 2 ya son saldos actuales. Si lo son, no cambies nada.
Si eran existencias totales iniciales, el préstamo pendiente del libro 1 y el del libro 2 requieren descontar una unidad cada uno: quedarían 2, 1, 4 y 2. Haz esa corrección una sola vez en Editar libro. El préstamo devuelto del libro 3 no reduce el saldo actual. No se incluye ajuste automático para evitar descontar dos veces.
No insertes préstamos ni devoluciones directamente en SQL Developer mientras usas el sistema: las operaciones hechas fuera de la aplicación no actualizan el saldo automáticamente.
El estado vencido se calcula en las pantallas/reportes con SYSDATE de Oracle; los registros existentes no se reescriben cada día. La fecha límite es inclusiva. El servidor y Windows deben tener fecha/zona horaria coherentes.
Fundación es una novela de ciencia ficción: si deseas corregir el ejemplo, cambia su categoría de Ciencias Naturales a Literatura.

## 6. Probar con Oracle
1. Registra una categoría, un autor, un estudiante y un libro con 1 ejemplar.
2. Asigna el autor al libro.
3. Presta ese libro: saldo 0. Ya no debe ofrecerse para otro préstamo.
4. Devuélvelo: saldo 1 y estado Devuelto.
5. Intenta repetir la devolución: debe rechazarse.
6. Prueba una fecha límite anterior al préstamo: no debe guardar ni descontar.
7. Filtra y exporta el historial; comprueba los datos en SQL Developer.

Pruebas automatizadas de lógica (sin una instancia Oracle):
```
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 7. Errores frecuentes
- ORA-01017: usuario/contraseña incorrectos.
- ORA-12514: nombre de servicio incorrecto; compáralo con SQL Developer.
- ORA-12541: listener detenido o host/puerto incorrectos.
- ORA-00942: conexión al usuario/esquema o servicio incorrecto, o faltan tablas.
- DPY-3010/DPY-3015: consulta compatibilidad del controlador; puede requerirse modo Thick con Oracle Instant Client. Configura ORACLE_CLIENT_LIB_DIR con la carpeta del cliente de 64 bits compatible con tu Python.
- ORA-00001 al insertar: revisa que las secuencias no estén detrás de MAX(id) si antes insertaste IDs manuales. Los triggers originales generan los IDs; el sistema no reinicia tus secuencias.

## Alcance y validación
Entrega de uso local, sin usuarios/login ni despliegue público. Escucha solo en 127.0.0.1. No recrea ni borra tus tablas. Las multas son manuales porque no se especificó tarifa. No usa una base de demostración ni datos simulados: requiere tu Oracle.
Las pruebas incluidas comprueban lógica con un doble de conexión. La conexión y ejecución real en tu base requieren configurar tus credenciales; no pueden verificarse desde la entrega.

Documentación del controlador: https://python-oracledb.readthedocs.io/en/stable/user_guide/connection_handling.html
