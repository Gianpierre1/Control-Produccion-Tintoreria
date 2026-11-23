# Propuesta: trazabilidad y ubicación de prendas en tiempo real

> **Estado:** borrador 1 (2026-11-23). Lo marcado como **[SUPUESTO]** no fue confirmado y debe validarse. Lo marcado como **[ABIERTO]** está sin decidir.
> **Alcance de la visión:** corte, costura, lavandería (en parte), acabados y estampados. **Fase 1: solo costura.**
> Parte del sistema de tablets y tickets descrito en `../costura/03-app-tablet.md`.

## 1. Problema y objetivo

**Problema.** Hoy no se sabe con certeza en qué etapa ni en qué puesto está cada prenda o paquete. Eso produce búsquedas manuales, esperas entre procesos que nadie ve y dificultad para responder "¿dónde está esta orden?" a producción o al cliente. **[SUPUESTO]** *Los datos concretos (cuánto tarda hoy una búsqueda, cuántos paquetes se extravían) no se han medido: se miden en la línea base de la fase 1.*

**Objetivo.** Saber, en cualquier momento, **dónde está y por dónde pasó** cada paquete (y, más adelante, cada prenda), con la hora de cada movimiento, para encontrarlo en segundos, ver cuánto espera entre procesos y avisar cuando se queda detenido.

## 2. Alcance

| Fase | Áreas | Qué se hace |
|---|---|---|
| **1** | **Costura** (más la impresión de tickets en corte) | Trazabilidad por paquete con QR, tablets en cada puesto, tablero de ubicación y alertas |
| 2 | Corte | Registrar el origen: orden, corte y generación de tickets |
| 3 | Lavandería, acabados y estampados | Escaneo al entrar y salir de cada área; identificador que resista agua y calor si hace falta |
| 4 | Despacho y cliente | Estado de la orden y consulta externa **[ABIERTO]** |

**Unidad de seguimiento. [SUPUESTO]** En la fase 1 es el **paquete** (un ticket). El seguimiento **por prenda** se deja para casos concretos (reproceso, prendas de alto valor) y para la fase 3, cuando haya que identificar la prenda en procesos con agua o calor.

## 3. Niveles de "tiempo real"

| Nivel | Cómo funciona | Qué sabes | Costo e infraestructura |
|---|---|---|---|
| **1. Por escaneo** | Cada operación o punto de control escanea el QR del ticket | Última etapa y puesto conocidos, con hora | Bajo: tablets y QR (ya diseñado) |
| 2. Por zonas | Lectores RFID fijos en puertas o mesas de cada área | En qué zona está, sin escanear a mano | Medio: lectores y una etiqueta por paquete o prenda |
| 3. Continuo | Localización en interior (UWB o balizas BLE) | Posición dentro de la planta | Alto: infraestructura propia y mantenimiento |

**Recomendación para la fase 1:** nivel 1. Cada vez que una costurera inicia o termina una operación, el sistema ya registra la ubicación y la hora. No requiere equipo nuevo. Si en el piloto se ve que se pierde mucho tiempo en traslados entre líneas, se evalúa agregar el nivel 2 solo en esos puntos.

> "Tiempo real" en el nivel 1 significa **última posición conocida**: la ubicación es tan fresca como el último escaneo. Un paquete que se mueve sin escanearse aparece en su posición anterior hasta el siguiente registro. Por eso se incluyen las alertas de paquetes sin movimiento.

## 4. Solución propuesta para la fase 1 (costura)

### 4.1 Flujo

1. **Corte → ticket:** el sistema genera un ticket por paquete a partir de la orden del ERP (SQL Server). El ticket se imprime donde se arman los paquetes **[SUPUESTO: en corte]** y viaja con el paquete.
2. **Puntos de control en costura** (cada uno registra un evento con hora, puesto y operaria):
   - recepción del paquete en la línea;
   - inicio y fin de cada operación (ya existe en la app);
   - control de calidad **[ABIERTO: si hay punto de revisión]**;
   - salida de la línea hacia el siguiente proceso.
3. **Ubicación actual:** la última lectura de cada ticket.
4. **Tablero en tiempo real** por línea: paquetes en proceso, en espera y terminados.
5. **Búsqueda:** escribir o escanear un ticket y ver su ubicación actual y su historial completo.

### 4.2 Qué se reutiliza y qué se agrega

| Ya diseñado | Se agrega |
|---|---|
| Tickets con QR y dígito de control | Puntos de control no asociados a una operación (recepción, calidad, salida) |
| App de tablet y API con eventos idempotentes y sin conexión | Tabla de ubicaciones y tipos de evento de movimiento |
| Operaciones, pausas y eficiencia | Tablero de ubicación y de espera entre operaciones |
| Sincronización con SQL Server (por construir) | Alertas por paquete detenido |

### 4.3 Indicadores del tablero

- Paquetes por operación y por línea (trabajo en proceso).
- **Espera entre operaciones:** tiempo desde que termina una operación hasta que empieza la siguiente.
- Paquetes sin movimiento por más de X minutos (alerta) **[ABIERTO: umbral]**.
- Tiempo desde que el paquete entra a la línea hasta que sale.
- Tiempo medio para localizar un paquete.

### 4.4 Identificador por prenda (opción posterior)

Para seguir cada prenda por separado hay tres alternativas estudiadas: sticker con QR, clip al dobladillo por fricción y clip con imanes o resorte. Para procesos con agua o calor (fase 3), la opción realista es una etiqueta RFID textil. Detalle en la conversación de diseño de clips; **[ABIERTO]** decidir si se necesita seguimiento por prenda y en qué procesos.

## 5. Integración

- **ERP (SQL Server):** lectura de órdenes, estilos, rutas de operaciones y tiempos. Sincronización periódica del servidor, sin que las tablets toquen el ERP. Faltan los nombres de las tablas (ver `../costura/04-informacion-pendiente.md`).
- **Servidor local:** API, base de datos y tableros dentro de la red de la planta, sin nube.
- **Tablets:** una por puesto, con la app Android del sistema de costura.
- **Red:** WiFi en la nave con puntos de acceso, VLAN propia para las tablets.

## 6. Piloto y despliegue

| Etapa | Duración orientativa | Qué se hace | Criterio para pasar |
|---|---|---|---|
| 0. Línea base | 1–2 semanas | Medir cuánto cuesta hoy encontrar un paquete y cuánto espera entre operaciones | Cifras de partida registradas |
| 1. Un puesto | 1–2 semanas | Una tablet con tickets reales | Los escaneos coinciden con la realidad observada |
| 2. Una línea | 3–4 semanas | Tablets en toda la línea y tablero | Más del 95 % de paquetes con su última lectura reciente **[SUPUESTO: meta]** |
| 3. Costura completa | 1–2 meses | Todas las líneas | Estabilidad y adopción |

## 7. Beneficios esperados

Sin cifras confirmadas, se expresan como lo que se medirá en la línea base:

- Menos tiempo buscando paquetes.
- Menos tiempo de espera entre operaciones.
- Alertas antes de que un retraso llegue al cliente.
- Historial por paquete para reclamos y para revisar causas de retrasos o reproceso.
- Datos para decidir balanceo de líneas.

## 8. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Escaneos olvidados o tardíos | Que el escaneo sea el mismo gesto que iniciar y terminar la operación; alertas de paquete sin movimiento |
| QR dañado o ilegible | Impresión con buen contraste y tamaño mínimo; reimpresión controlada y auditada |
| Resistencia del personal | Comunicar el beneficio, no usarlo como vigilancia; la costurera ve sus propios datos y puede reclamar |
| WiFi insuficiente | Estudio de cobertura antes del despliegue; modo sin conexión en la tablet |
| No hay acceso a las tablas del ERP | Es el primer bloqueo hoy; ver preguntas abiertas |
| Costo de las tablets | Piloto de una línea antes de comprar para toda la planta |

## 9. Costos

No se incluyen cifras. Los rubros a cotizar en Perú son: tablets (con soporte y cargador), puntos de acceso WiFi, servidor, impresora de etiquetas e insumos, desarrollo de la app y del servidor, e instalación. Ver `../costura/01-hardware-modelos.md` para los modelos de red y servidor.

## 10. Preguntas abiertas

- [ ] ¿La unidad de seguimiento es el paquete (supuesto), la prenda o la partida?
- [ ] ¿Qué decisiones se tomarán con esta información? (buscar prendas, medir esperas, avisar al cliente, controlar plazos)
- [ ] ¿Dónde se arman los paquetes y se imprimen los tickets?
- [ ] ¿Hay punto de control de calidad en costura?
- [ ] ¿Quién consulta el tablero: supervisor de línea, jefe de planta, planeamiento?
- [ ] ¿Se necesita seguimiento por prenda y en qué procesos?
- [ ] Tablas de SQL Server (ver el documento de información pendiente de costura).
- [ ] Formato final de la propuesta (documento o presentación) y destinatarios.
