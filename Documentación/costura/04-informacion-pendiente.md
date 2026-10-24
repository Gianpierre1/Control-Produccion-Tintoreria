# Información pendiente para continuar (app de tablet de Costura)

> **Para quien lea esto (otro chat o persona):** este documento es autónomo. Explica el proyecto en pocas líneas, lista lo que falta saber y da el formato exacto de la respuesta. Responde en un archivo llamado `05-respuestas.md` siguiendo la plantilla de la sección 5. No incluyas contraseñas ni datos personales de trabajadoras.

## 1. Contexto del proyecto

Una planta textil en Perú quiere medir, por costurera y por día, los **minutos trabajados** y los **minutos improductivos** en Costura, para calcular la **eficiencia compensada** y pagar un incentivo.

- Cada costurera tendrá una **tablet Android** conectada por WiFi a un **servidor local** (sin nube).
- La costurera inicia sesión con gafete y PIN, **escanea el ticket de un paquete de prendas**, y la tablet le muestra la orden, el color, la talla, la cantidad y las **operaciones** a realizar con su **SMV** (minutos estándar por pieza).
- Registra inicio y fin de la operación, las piezas hechas y las paradas con su causa.
- El servidor calcula: `Min. estándar = piezas × SMV`, y `Eficiencia compensada = Min. estándar ÷ (Min. trabajados − Min. improductivos)`.
- **Los tickets aún no existen**: los genera el sistema a partir de las órdenes de producción del ERP.
- Los datos del ERP están en **SQL Server**. El servidor los copiará periódicamente, solo en lectura.

Estado actual en el repositorio: documentación en `Documentación/costura/` (el diseño vigente es `03-app-tablet.md`), y código con tests en `Scripts/costura/` (fórmulas, cálculo de minutos a partir de eventos, generación de códigos de ticket y una API REST con almacenamiento en memoria). Falta la sincronización con SQL Server, la base PostgreSQL real y la app Android.

## 2. Qué necesito saber

### 2.1 SQL Server (lo más urgente)

Necesito identificar, en la base del ERP, dónde están estos datos y cómo se llaman:

| Dato | Para qué se usa |
|---|---|
| Órdenes de producción de costura (código de orden, estilo, cliente) | Origen de los tickets |
| Colores y tallas de cada orden, con su cantidad | Dividir la orden en paquetes con ticket |
| Ruta de operaciones de cada estilo (secuencia y nombre de la operación) | Mostrar las operaciones en la tablet |
| SMV de cada operación (minutos estándar por pieza) | Calcular minutos estándar |
| Trabajadoras (código, nombre, gafete) | Inicio de sesión |
| Puestos o máquinas de costura (si existen) | Asignación operaria-puesto |
| Piezas producidas históricas (si existen) | Comparar con lo que registre la tablet |

Para ayudar a ubicarlo, se pueden ejecutar estas consultas **de solo lectura** y pegar el resultado (sin datos de personas):

```sql
-- 1. Tablas y vistas de la base (ajustar el nombre de la base)
SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
FROM INFORMATION_SCHEMA.TABLES
ORDER BY TABLE_SCHEMA, TABLE_NAME;

-- 2. Buscar tablas relacionadas con costura, operaciones, SMV, órdenes y tickets
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME LIKE '%OPERAC%' OR TABLE_NAME LIKE '%RUTA%' OR TABLE_NAME LIKE '%ORDPRO%'
   OR TABLE_NAME LIKE '%ORDEN%'  OR TABLE_NAME LIKE '%COSTURA%' OR TABLE_NAME LIKE '%TRABAJ%'
   OR COLUMN_NAME LIKE '%SMV%'   OR COLUMN_NAME LIKE '%MINUTO%' OR COLUMN_NAME LIKE '%ESTANDAR%'
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION;
```

> Referencia: los exportes `Data/Tintorería.csv` y `Data/Acabados.csv` del repositorio ya tienen columnas como `COD_ORDPRO`, `COD_USUARIO` y `MAQUINA`, lo que sugiere que el ERP usa esos nombres. Esos archivos son de Tintorería y Acabados; **no incluyen Costura**.

### 2.2 Decisiones de negocio

| # | Pregunta | Opciones o ejemplo |
|---|---|---|
| 1 | ¿Un ticket por **paquete** que recorre toda la ruta, o un ticket por **operación**? | Un ticket por paquete (la costurera elige la operación) / un ticket por operación |
| 2 | ¿Cuántas prendas lleva un paquete? | Número fijo (p. ej. 30) o distinto según estilo |
| 3 | ¿Cómo se imprimirán los tickets? | Impresora de etiquetas (modelo) / hojas A4 con varios tickets |
| 4 | ¿Qué paradas **se descuentan** de los minutos trabajados para pagar? | Solo las compensables (material, máquina) / todas las que tengan causa |
| 5 | Lista de causas de parada y cuáles son compensables | Material, Máquina, Reproceso, Otro, ¿SS.HH.?, ¿permiso?, ¿capacitación? |
| 6 | ¿Cuánto es la **manipulación del ciclo** aceptable entre operaciones? | 60 a 90 s (propuesto: 90 s) |
| 7 | ¿Tiempo máximo de hueco sin actividad antes de preguntar la causa? | p. ej. 3 minutos |
| 8 | ¿Descansos planificados (hora y duración)? | Refrigerio, pausas |
| 9 | ¿Cómo se identifica la costurera? | PIN, gafete QR, ambos |
| 10 | ¿Las operaciones se asignan fijas a cada costurera o rota? | Fija / rota |

### 2.3 Tablet y planta

| # | Pregunta |
|---|---|
| 11 | ¿Número de líneas, puestos y costureras? ¿Cuántas para el piloto? |
| 12 | ¿Modelo y presupuesto de tablet? (candidatas sin confirmar: Samsung Galaxy Tab A9+, Lenovo Tab M10 Plus 3.ª gen., Samsung Galaxy Tab Active5) |
| 13 | ¿Hay WiFi en la planta? ¿Cobertura y marca de los puntos de acceso? |
| 14 | ¿Sistema operativo y recursos del servidor? (se propone Ubuntu Server 24.04) |
| 15 | ¿Quién administra la red (TI interna o externa)? |

### 2.4 Legal y laboral

| # | Pregunta |
|---|---|
| 16 | ¿Se informará a las trabajadoras sobre el uso de sus datos de tiempo (Ley 29733)? ¿Quién lo valida? |
| 17 | ¿Cómo se atenderán los reclamos de las costureras sobre sus minutos? |

## 3. Qué haré con las respuestas

1. Con la 2.1: sincronización de órdenes, estilos, rutas, SMV y trabajadoras desde SQL Server a PostgreSQL.
2. Con la 2.2: ajustar la generación de tickets, la política de minutos improductivos y los umbrales.
3. Con la 2.3: dimensionar la red, las tablets y el servidor.
4. Con la 2.4: agregar la sección de privacidad y el procedimiento de reclamos.

## 4. Lo que **no** debe incluir la respuesta

- Contraseñas, cadenas de conexión con credenciales o tokens.
- Nombres, DNI o datos personales de trabajadoras (basta con los nombres de columnas y tablas).
- Datos financieros ni precios de clientes.

## 5. Plantilla de respuesta (`05-respuestas.md`)

```markdown
# Respuestas

## SQL Server
- Base de datos y esquema principal: ...
- Órdenes de producción: tabla/vista `...`, columnas: ...
- Colores y tallas: tabla/vista `...`, columnas: ...
- Ruta de operaciones: tabla/vista `...`, columnas: ...
- SMV: tabla/vista `...`, columna: ...
- Trabajadoras: tabla/vista `...`, columnas (sin datos personales): ...
- Puestos o máquinas: tabla/vista `...`, columnas: ...
- Piezas producidas históricas: tabla/vista `...`, columnas: ...
- Resultado de las consultas 1 y 2: (pegar aquí)

## Decisiones de negocio
1. ...
2. ...
(continuar hasta la 10)

## Tablet y planta
11. ...
(continuar hasta la 15)

## Legal y laboral
16. ...
17. ...

## Dudas o comentarios
- ...
```
