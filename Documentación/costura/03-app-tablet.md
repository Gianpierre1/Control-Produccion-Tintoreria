# App de tablet para costura (cambio de enfoque, 2026-10-24)

> **Decisión:** la tablet reemplaza el sistema anterior de sensores y cámaras (documentos 00–02). Cada costurera tiene su tablet, escanea el ticket de la prenda y registra inicio, fin, piezas y paradas. Los tickets los genera el propio sistema. Los datos del ERP vienen de **SQL Server**.
>
> Los documentos 00–02 se conservan como alternativa. Lo que sigue vigente de ellos: fórmulas de eficiencia (00, sección 2), catálogo de causas, auditoría y reclamos.

## 1. Qué cambia y qué se pierde

| Antes (sensores + cámaras) | Ahora (tablet) |
|---|---|
| El tiempo lo mide la pinza de corriente y la cámara | El tiempo lo registra la costurera al escanear y marcar |
| Dato objetivo, difícil de alterar | Dato **declarado**: depende de que la costurera marque a tiempo |
| La causa se registraba con botones | La causa se elige en la tablet |
| Piezas desde ERP o tickets manuales | Piezas desde el ticket escaneado |

**Riesgo principal:** al ser un dato declarado, un olvido o una marca tardía distorsiona los minutos que pagan el incentivo. Controles previstos (sección 6):
- El sistema pregunta por qué hay un hueco sin actividad, y no deja que se acumule sin causa.
- El supervisor valida y corrige con auditoría; la costurera ve sus propios números y puede reclamar.
- Se contrasta con un estudio de tiempos manual en el piloto (error diario por operaria dentro de ±3–5 %).
- Si la zona gris resulta alta, se puede volver a agregar sensores sin cambiar la app: las paradas entrarían como otra fuente (`fuente = 'sensor'`).

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
4. **Terminar:** *Terminar* con las piezas hechas (por defecto, la cantidad del ticket). Pasa al siguiente.
5. **Parada:** *Parar* y elegir causa (Material, Máquina, Reproceso, Otro; catálogo configurable). *Reanudar* cierra la parada.
6. **Hueco sin actividad:** si pasan más de N minutos sin operación ni parada, la app pregunta la causa. Si no responde, queda como *parada sin causa* y se avisa al supervisor.
7. **Descanso y fin de jornada:** marcan el cierre; los descansos planificados no cuentan como trabajados.
8. **Resumen del día:** muestra sus minutos, piezas y eficiencia, con las mismas fórmulas oficiales.

## 4. Tickets generados por el sistema

- **Origen:** la orden de producción sincronizada desde el ERP, dividida en paquetes por color y talla (tamaño de paquete configurable; el último paquete lleva el resto).
- **Código:** `T` + 8 dígitos + dígito de control (validación local en la app, sin red). El código solo identifica el ticket; el contenido se consulta en el servidor.
- **Impresión:** desde una pantalla web de administración, en impresora de etiquetas o en hojas A4 con varios tickets, con QR y texto legible (orden, color, talla, cantidad).
- **Operaciones del ticket:** al crearlo se copia la ruta de operaciones con su SMV; los cambios posteriores en el ERP no alteran un ticket ya emitido.
- **Reproceso:** un ticket de reproceso referencia al original (`ticket_origen_id`) y lleva la causa.
- **Anulación y reimpresión:** un ticket anulado deja de aceptar escaneos. Cada reimpresión queda auditada.
- **[ABIERTO]** Si cada ticket cubre toda la ruta de la prenda o hay un ticket por operación.

## 5. API REST (v1)

Autenticación: cada tablet se registra una vez (el administrador la aprueba y recibe un token de dispositivo); la costurera inicia sesión con PIN y obtiene un token corto. HTTPS con certificado de una CA local, o HTTP solo dentro de una VLAN aislada.

| Método y ruta | Uso |
|---|---|
| `POST /api/v1/dispositivos` | Registrar una tablet (pendiente de aprobación) |
| `POST /api/v1/sesion` | Iniciar sesión (gafete o PIN); devuelve token y hora del servidor |
| `GET  /api/v1/tickets/{codigo}` | Datos del ticket y operaciones pendientes |
| `GET  /api/v1/causas` | Catálogo de causas |
| `POST /api/v1/eventos` | Enviar un lote de eventos (idempotente por `event_id`) |
| `GET  /api/v1/resumen/hoy` | Resumen del día de la costurera |
| `POST /api/v1/reclamos` | Reclamar un segmento |
| `POST /api/v1/ordenes/{op}/tickets` | (administración) Generar los tickets de una orden |
| `GET  /api/v1/tickets/{id}/pdf` | (administración) Etiqueta imprimible |
| `POST /api/v1/tickets/{id}/anular` | (administración) Anular ticket |

Eventos (`tipo`): `JORNADA_INICIO`, `JORNADA_FIN`, `DESCANSO_INICIO`, `DESCANSO_FIN`, `OP_INICIO`, `OP_FIN` (con `piezas`), `PARADA_INICIO` (con `causa`), `PARADA_FIN`.

```json
POST /api/v1/eventos
[{"event_id": "uuid", "tipo": "OP_INICIO", "ts": "2026-10-26T08:03:12-05:00",
  "ticket_operacion_id": 1201},
 {"event_id": "uuid", "tipo": "OP_FIN", "ts": "2026-10-26T08:41:50-05:00",
  "ticket_operacion_id": 1201, "piezas": 20}]
```

## 6. Cálculo de minutos a partir de los eventos

Implementado en `Scripts/costura/segmentos.py` (con tests).

| Concepto | Regla |
|---|---|
| Min. trabajados | Jornada − descansos planificados |
| Min. estándar | Σ piezas × SMV de cada `OP_FIN` |
| Operación en curso | Tiempo entre `OP_INICIO` y `OP_FIN`; cuenta como trabajado |
| Hueco corto entre operaciones | Menor al umbral (90 s por defecto): manipulación del ciclo, no es improductivo |
| Parada con causa | Improductiva; se descuenta si la causa es `compensable` (política abierta: todas o solo compensables) |
| Hueco largo o parada sin causa | No se compensa; sale en la alerta al supervisor |
| Operación abierta al cerrar la jornada | Se cierra en la hora de fin de jornada |

Eficiencia compensada = Min. estándar ÷ (Min. trabajados − Min. improductivos), con las fórmulas de `formulas.py`.

## 7. App Android

- **Lenguaje y UI:** Kotlin con Jetpack Compose.
- **Datos locales:** Room (SQLite) para eventos pendientes; WorkManager para enviarlos en segundo plano con reintentos.
- **Escaneo:** ML Kit (cámara de la tablet); soporte para lector Bluetooth o USB como alternativa.
- **Modo quiosco:** solo la app visible (bloqueo de tarea de Android Enterprise); sin acceso a otras apps.
- **Pantallas:** inicio de sesión · escaneo · ticket y operaciones · operación en curso (cronómetro, parar, terminar) · causa de parada · resumen del día.
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
- [ ] Impresora de etiquetas o impresión en hojas.
- [ ] Modelo de tablet y cantidad para el piloto.
- [ ] Tiempo máximo de hueco antes de preguntar la causa; umbral de manipulación (60–90 s).
- [ ] Qué causas son compensables (política de la sección 6).
- [ ] Cómo se identifica a la costurera: PIN, gafete QR o ambos.
- [ ] Legal (Ley 29733): informar el uso de los datos de tiempo de cada trabajadora.
