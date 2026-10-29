# App de tablet para costura (cambio de enfoque, 2026-10-24)

> **Decisión:** la tablet reemplaza el sistema anterior de sensores y cámaras (documentos 00–02). Desde 2026-10-28 **no hay minutos improductivos**: se mide el tiempo de cada operación contra su tiempo asignado. Cada costurera tiene su tablet, escanea el ticket de la prenda y registra inicio, fin, piezas y pausas. Los tickets los genera el propio sistema. Los datos del ERP vienen de **SQL Server**.
>
> Los documentos 00–02 se conservan como alternativa. Lo que sigue vigente de ellos: la regla de sumar minutos y nunca promediar porcentajes, la auditoría y los reclamos. Las fórmulas con minutos improductivos (00, sección 2) ya no aplican.

## 1. Modelo de medición (actualizado 2026-10-28)

No hay minutos improductivos. Cada operación de un ticket tiene un **tiempo asignado** y la eficiencia depende de qué tan rápido la terminó la costurera.

- **Tiempo asignado** = piezas hechas × minutos por pieza. Los minutos por pieza salen de una **tabla de tarifas** según el **tipo de operación**, la **cantidad de prendas** del ticket y el **tipo de prenda** (ver sección 6).
- **Pausas:** hay motivos de parada (baño, falla de máquina, falta de material, refrigerio, reunión, otro; se pueden agregar más). La costurera pausa la operación con un botón en la tablet y elige el motivo. **Cada motivo tiene un tiempo permitido para volver, y aplica a cada pausa por separado.** Si regresa dentro de ese tiempo, la pausa no cuenta: el reloj de la operación se detiene y continúa.
- **Exceso:** si se pasa del tiempo permitido, el exceso cuenta como tiempo real. *(Política por confirmar.)*
- **Tiempo real** = tiempo entre *Iniciar* y *Terminar* − pausas dentro de lo permitido.
- **Eficiencia de la operación** = tiempo asignado ÷ tiempo real. Más de 100 % = terminó antes de lo asignado.
- **Eficiencia del día** = Σ tiempo asignado ÷ Σ tiempo real (minutos sumados, nunca promedio de porcentajes).

**Riesgo:** el tiempo lo declara la costurera con la tablet. Controles: la pausa exige motivo, el exceso queda registrado y visible al supervisor, el supervisor corrige con auditoría, la costurera ve sus números y puede reclamar, y el piloto se contrasta con un cronometraje manual.

## 2. Arquitectura

```
Tablet Android ──WiFi──> AP PoE ──> switch ──> Servidor local
(Kotlin, offline-first)                       ├─ API REST (Python, FastAPI)
                                              ├─ PostgreSQL
                                              ├─ Servicio de sincronización ←── ERP (SQL Server)
                                              └─ Tableros (Grafana) y exportación a planilla
```

- **La tablet nunca habla con el ERP.** El servidor copia de SQL Server (solo lectura) las órdenes, estilos, rutas de operaciones y SMV a su propia base.
- **Offline-first:** la app guarda cada evento en la tablet (base local) y los envía cuando hay WiFi. El servidor ignora los eventos repetidos (mismo `event_id`).
- **Reloj:** cada evento lleva la hora de la tablet y el servidor guarda la hora de recepción y la diferencia con su propio reloj. La app sincroniza hora con el servidor al iniciar sesión.

## 3. Flujo de uso

1. **Inicio de jornada:** la costurera inicia sesión con PIN o gafete (QR). Queda registrado el inicio de jornada y su puesto.
2. **Escanear el ticket:** la app muestra orden, estilo, color, talla, cantidad y las operaciones pendientes de la ruta.
3. **Iniciar la operación:** elige la operación (la app resalta la que corresponde a su puesto) y marca *Iniciar*.
4. **Pausar:** *Pausar* y elegir el motivo. La app muestra cuánto tiempo tiene para volver y avisa cuando se acaba. *Reanudar* continúa la operación.
5. **Terminar:** *Terminar* con las piezas hechas (por defecto, la cantidad del ticket). No se puede terminar con una pausa abierta.
6. **Resumen del día:** muestra sus operaciones, piezas, tiempo asignado, tiempo real y eficiencia.

## 4. Tickets generados por el sistema

- **Origen:** la orden de producción sincronizada desde el ERP, dividida en paquetes por color y talla (tamaño de paquete configurable; el último paquete lleva el resto).
- **Código:** `T` + 8 dígitos + dígito de control (validación local en la app, sin red). El código solo identifica el ticket; el contenido se consulta en el servidor.
- **Impresión:** desde una pantalla web de administración, en impresora de etiquetas o en hojas A4 con varios tickets, con QR y texto legible (orden, color, talla, cantidad).
- **Operaciones del ticket:** al crearlo se copia la ruta de operaciones con su SMV; los cambios posteriores en el ERP no alteran un ticket ya emitido.
- **Reproceso:** un ticket de reproceso referencia al original (`ticket_origen_id`) y lleva el motivo.
- **Anulación y reimpresión:** un ticket anulado deja de aceptar escaneos. Cada reimpresión queda auditada.
- **[ABIERTO]** Si cada ticket cubre toda la ruta de la prenda o hay un ticket por operación.

## 5. API REST (v1)

Autenticación: cada tablet se registra una vez (el administrador la aprueba y recibe un token de dispositivo); la costurera inicia sesión con PIN y obtiene un token corto. HTTPS con certificado de una CA local, o HTTP solo dentro de una VLAN aislada.

| Método y ruta | Uso |
|---|---|
| `POST /api/v1/dispositivos` | Registrar una tablet (pendiente de aprobación) |
| `POST /api/v1/sesion` | Iniciar sesión (gafete o PIN); devuelve token y hora del servidor |
| `GET  /api/v1/tickets/{codigo}` | Datos del ticket y operaciones pendientes |
| `GET  /api/v1/motivos` | Motivos de pausa activos y su tiempo permitido |
| `POST/PUT /api/v1/motivos` | (administración) Agregar un motivo, cambiar su tiempo o darlo de baja |
| `POST/GET /api/v1/tarifas` | (administración) Crear y listar tarifas de tiempo asignado |
| `PUT  /api/v1/tarifas/{id}` | (administración) Cerrar la vigencia de una tarifa |
| `POST /api/v1/eventos` | Enviar un lote de eventos (idempotente por `event_id`) |
| `GET  /api/v1/resumen/hoy` | Resumen del día de la costurera |
| `POST /api/v1/reclamos` | Reclamar un segmento |
| `POST /api/v1/ordenes/{op}/tickets` | (administración) Generar los tickets de una orden |
| `GET  /api/v1/tickets/{id}/pdf` | (administración) Etiqueta imprimible |
| `POST /api/v1/tickets/{id}/anular` | (administración) Anular ticket |

Eventos (`tipo`): `JORNADA_INICIO`, `JORNADA_FIN` (asistencia, no entran en la eficiencia), `OP_INICIO`, `OP_FIN` (con `piezas`), `PAUSA_INICIO` (con `motivo`), `PAUSA_FIN`.

```json
POST /api/v1/eventos
[{"event_id": "uuid", "tipo": "OP_INICIO", "ts": "2026-10-26T08:03:12-05:00",
  "ticket_operacion_id": 1201},
 {"event_id": "uuid", "tipo": "OP_FIN", "ts": "2026-10-26T08:41:50-05:00",
  "ticket_operacion_id": 1201, "piezas": 20}]
```

## 6. Cálculo (implementado en `Scripts/costura/operaciones.py`, con tests)

| Concepto | Regla |
|---|---|
| Tiempo asignado | piezas × minutos por pieza del ticket-operación (valor tomado de la tarifa al emitir el ticket) |
| Tarifa | La más específica que aplica: tipo de prenda exacto, rango de cantidad más angosto, vigencia más reciente; sin tarifa o ambigua, no se emite el ticket |
| Cambiar un tiempo | Se cierra la vigencia de la tarifa y se crea otra; los tickets ya emitidos no cambian |
| Motivos | Se agregan, cambian o se dan de baja por la API de administración; los eventos antiguos con un motivo dado de baja se siguen calculando |
| Pausa dentro del permitido | No cuenta (se descuenta del tiempo real) |
| Pausa fuera del permitido | El exceso cuenta como tiempo real y se marca para el supervisor |
| Operación sin terminar | No entra en la eficiencia; aparece como operación abierta |
| Terminar con pausa abierta | No se permite: hay que reanudar primero |
| Eficiencia del día | Σ asignado ÷ Σ real |

## 7. App Android

- **Lenguaje y UI:** Kotlin con Jetpack Compose.
- **Datos locales:** Room (SQLite) para eventos pendientes; WorkManager para enviarlos en segundo plano con reintentos.
- **Escaneo:** ML Kit (cámara de la tablet); soporte para lector Bluetooth o USB como alternativa.
- **Modo quiosco:** solo la app visible (bloqueo de tarea de Android Enterprise); sin acceso a otras apps.
- **Pantallas:** inicio de sesión · escaneo · ticket y operaciones · operación en curso (cronómetro, pausar, terminar) · motivo de pausa · resumen del día.
- **Textos grandes y botones amplios:** se usa de pie o sentada, con las manos ocupadas.

### Tablet (decisión pendiente)

Requisitos mínimos: Android 10 o superior, pantalla de 8–10", cámara trasera con autofocus, WiFi 5 (ac) o superior, batería para un turno, soporte para modo quiosco.
Candidatas ⚠️ (confirmar disponibilidad, precio y soporte en Perú): Samsung Galaxy Tab A9+, Lenovo Tab M10 Plus (3.ª gen.), y Samsung Galaxy Tab Active5 si se necesita versión reforzada.

**Costo:** una tablet por costurera son ~400 equipos para la planta completa. Para el piloto se parte con una línea (~25).

## 8. Red

- WiFi en el techo con puntos de acceso PoE (8–10 para ~400 tablets; dimensionar con un estudio de cobertura).
- VLAN propia para tablets, con acceso solo al servidor.
- Nombre fijo del servidor en la red local y reserva de IP por tablet.
- Hora sincronizada con NTP en el servidor.
- Las cámaras y sensores de los documentos 01–02 dejan de ser necesarios, salvo que se reactive esa alternativa.

## 9. Piloto

1. **Un puesto, una semana:** una tablet y una costurera; se comparan los minutos registrados con un cronometraje manual del mismo día.
2. **Una línea (~25 tablets):** se mide la zona gris, el tiempo de captura y el error frente al estudio manual (±3–5 %).
3. **Paralelo 2–3 meses:** el sistema registra y se paga con el método actual.
4. **Puesta en marcha** con procedimiento de reclamo.

## 10. Preguntas abiertas

- [ ] **SQL Server:** nombres de las tablas o vistas de órdenes de producción, estilos, colores, tallas, rutas de operaciones y SMV; usuario de solo lectura.
- [ ] Un ticket por prenda o por operación; tamaño de paquete.
- [ ] **Confirmar los tiempos permitidos** de los motivos iniciales (los actuales son provisionales: baño 10, falla de máquina 30, falta de material 20, refrigerio 60, reunión 30, otro 10 minutos).
- [ ] Qué pasa con el exceso: ¿cuenta como tiempo real, o lo valida el supervisor?
- [ ] Valores reales de la tabla de tarifas: minutos por pieza por operación, tipo de prenda y rango de cantidad (¿existen en el ERP?).
- [ ] Impresora de etiquetas o impresión en hojas.
- [ ] Modelo de tablet y cantidad para el piloto.
- [ ] Cómo se identifica a la costurera: PIN, gafete QR o ambos.
- [ ] Legal (Ley 29733): informar el uso de los datos de tiempo de cada trabajadora.
