# Brief técnico: medición de tiempos improductivos en Costura

> Fuente de verdad del proyecto. Lo marcado como **[ABIERTO]** no está decidido y no debe asumirse.
> **Cambio de enfoque (2026-10-24):** la medición pasa a una app de tablet por costurera; ver [03-app-tablet.md](03-app-tablet.md). Los sensores y cámaras de este brief quedan como alternativa. Las fórmulas (sección 2), el catálogo de causas, los reclamos y la auditoría siguen vigentes.
> Presentación asociada: *Tiempos_improductivos_Costura_3.pptx* (propuesta A/B/C, octubre 2026).
> Documentos complementarios: [01-hardware-modelos.md](01-hardware-modelos.md) · [02-integracion-y-red.md](02-integracion-y-red.md)

## 1. Objetivo

Registrar automáticamente, por operaria y por día, los **minutos trabajados** y los **minutos improductivos** en Costura. Con ellos se calcula la **eficiencia compensada**, de la que depende el pago del incentivo.

- Los datos pagan incentivo, así que deben ser **auditables**: cada minuto improductivo tiene origen, hora, puesto y causa.
- El sistema **protege el incentivo**: reconoce las paradas que no son culpa de la operaria. No es vigilancia.
- Todo corre en la **red local de la planta**, sin internet ni nube.

## 2. Fórmulas de eficiencia (oficiales; no cambiar)

| Indicador | Fórmula | Nivel |
|---|---|---|
| Eficiencia real | Σ Min. estándar ÷ Σ Min. trabajados | Siempre con minutos sumados, **nunca promediando %** |
| % Tiempo improductivo | Σ Min. improductivos ÷ Σ Min. trabajados | Igual |
| Eficiencia compensada | Min. estándar ÷ (Min. trabajados − Min. improductivos) | Por trabajador y día |
| Compensada agregada (semana, línea, trabajador) | Σ (Compensada × Min. trabajados) ÷ Σ Min. trabajados | Ponderado por minutos, solo minutos con dato |
| Incentivo | Σ Incentivo | Suma directa |

- Min. estándar = piezas producidas × SMV de la operación.
- Datos del ERP (corte 2026-08-09 en adelante): compensada = Std ÷ (Trab − Improd).
- Histórico del Excel: se toma el valor del Excel, **sin recalcular**.
- **[ABIERTO]** ¿Se restan todos los minutos improductivos o solo los de ciertas causas? El catálogo de causas tiene el campo `compensable` para soportar ambas políticas.

Valores de validación (están en los tests): estándar 400, trabajados 480:

| Improductivos | Compensada |
|---|---|
| 60 | 400 / 420 = **95.24 %** |
| 20 | 400 / 460 = **86.96 %** |
| 100 | 400 / 380 = **105.26 %** |

## 3. Estados del puesto

| Estado | Cómo se detecta | ¿Improductivo? |
|---|---|---|
| Cosiendo | Picos de corriente del motor | No |
| Manipulación del ciclo | Máquina sin coser menos del umbral (60–90 s, por operación) | No (está en el SMV) |
| Parada justificada | Parada larga con causa registrada | Sí, compensable según catálogo |
| Parada sin causa | Parada larga sin causa → alerta al supervisor | Pendiente de validación |
| Ausente | Sin persona en la zona más de X min (configurable) | Según política (SS.HH., permiso) |
| Máquina apagada | Sin consumo de corriente | Según causa |

Con la operaria sentada y la máquina parada, la cámara decide: **trabajando** (manipula la pieza), **inactiva** o **ausente**.

## 4. Arquitectura

**Base (A) + cámara cenital (C).** B (cámara por máquina con fotos en paradas largas) queda como alternativa si la vista cenital falla en el piloto.

```
[Por máquina]  ESP32 + pinza SCT-013 (+ radar LD2410C opcional) + botonera de causas
                    │ WiFi o Ethernet, MQTT (pocos datos)
[Por 4 puestos] Cámara cenital ──cable PoE──> Switch PoE
                    │ HTTP/RTSP
[Servidor local, PC con GPU]
   Mosquitto → servicio de reglas → PostgreSQL/TimescaleDB → Grafana + exportación a planilla
   Servicio de visión (imagen → pose → regla por zona) → eventos por MQTT
```

- El modelo de visión corre **solo en el servidor** (no en cámara, ESP32 ni nube).
- **No se guarda video.** Solo eventos y, opcionalmente, foto de paradas en disputa con retención limitada (p. ej. 30 días).
- Video por cable PoE en árbol (switch central + switches PoE por zona). Sin hubs ni repartidores pasivos. Cámaras en su propia VLAN.

## 5. Software a desarrollar

### 5.1 Firmware ESP32
- Muestreo de corriente, Irms y publicación del estado cada 1 s (o al cambiar) por MQTT.
- Umbrales por máquina (apagada / encendida sin coser / cosiendo), ajustables por MQTT.
- Botones de causa → evento MQTT con código.
- Cola local si cae la red; reenviar con la marca de tiempo original (NTP).
- Actualización OTA.

Tópicos MQTT:
```
planta/{linea}/{puesto}/maquina    {"ts": "...", "estado": "cosiendo|encendida|apagada", "irms": 1.23}
planta/{linea}/{puesto}/causa      {"ts": "...", "codigo": "MAT|MAQ|REP|OTR", "event_id": "uuid"}
planta/{linea}/{puesto}/presencia  {"ts": "...", "presente": true}
planta/vision/{puesto}             {"ts_inicio": "...", "ts_fin": "...", "estado": "trabajando|inactiva|ausente", "confianza": 0.0}
```

### 5.2 Servicio de visión (Python)
- Leer imágenes/flujo de cada cámara a ~5 fps (menos si se consulta solo cuando la máquina no cose).
- Pose preentrenada (persona + muñecas): RTMPose o MediaPipe (Apache-2.0). Ultralytics YOLO-pose es AGPL-3.0: revisar licencia.
- ONNX Runtime (CUDA) o TensorRT; OpenVINO sin GPU.
- Zonas poligonales por puesto en un archivo de configuración por cámara.
- Reglas: sin persona más de X s → ausente; desplazamiento de muñecas normalizado por tamaño de persona, ventana de 1 s, contra umbral → trabajando/inactiva; con histéresis y duración mínima.
- Solo decide cuando la pinza indica **no cosiendo**.
- Herramienta de calibración: un día grabado **solo para el piloto**, etiquetado y comparado con la regla.

### 5.3 Servicio de reglas y base de datos
- **[ABIERTO]** Servicio en Python con tests unitarios (sugerido) frente a Node-RED (mencionado en las propuestas).
- Une señales (máquina, causa, presencia, visión) en **segmentos de estado** por puesto.
- Asigna segmentos a la operaria según la asignación por turno.
- Resumen diario por operaria con las fórmulas de la sección 2.
- Alerta al supervisor por parada larga sin causa.
- **Reclamos**: la operaria o el supervisor corrige un segmento, con auditoría (quién y cuándo).
- Modelo de datos: ver `Scripts/costura/schema.sql`.

### 5.4 Tableros y salida
- Grafana: estado en vivo por línea, minutos improductivos por causa, ranking de paradas sin causa, eficiencias del día.
- Exportación diaria a la planilla de pago. **[ABIERTO]** formato (Excel o integración con el ERP).

## 6. Validación antes de pagar con los datos

1. Línea base: estudio de tiempos manual en la línea piloto (semanas 1–2).
2. Prototipo: 3–5 nodos + 1 cámara cenital grabando un día (semanas 2–4).
3. Piloto de línea completa con la base (A); medir la **zona gris** = paradas sin causa + tiempo en disputa (semanas 4–8).
4. Decisión: zona gris > 3–5 % → agregar cámara cenital (C), o B si la cenital no acierta.
5. Paralelo 2–3 meses: el sistema registra, se paga con el método actual.
6. Aceptación: error del tiempo improductivo diario por operaria dentro de **±3–5 %** frente al estudio manual.

## 7. Privacidad y aspectos laborales

- Ley 29733 (Perú): informar a las trabajadoras sobre cámaras, finalidad y plazo de retención. Validar con asesoría legal.
- Sin video almacenado; acceso limitado a Supervisión e Ingeniería; todo cambio auditado.
- Comunicación del proyecto: el sistema protege el incentivo.

## 8. Preguntas abiertas (checklist)

- [ ] Número de líneas y máquinas; marcas/modelos de máquinas y motores.
- [ ] Causas compensables (sección 2).
- [ ] Origen de SMV, piezas producidas y asignaciones (¿ERP?, ¿API o exportación?).
- [ ] Formato de salida a la planilla de pago.
- [ ] Red existente y SO del servidor (se sugiere Ubuntu Server).
- [ ] Umbrales iniciales: parada corta por operación, tiempo de ausencia, umbral de movimiento (se calibran en el piloto).
- [ ] Servicio de reglas: Python vs Node-RED.
- [ ] Altura de las luminarias y distribución real de puestos (define lente y cobertura de cada cámara).

## 9. Orden de desarrollo

1. Esquema de BD + cálculo de fórmulas con tests *(implementado en `Scripts/costura/`)*.
2. Ingesta MQTT + servicio de reglas con datos simulados.
3. Firmware ESP32 (corriente + botones) y calibración.
4. Grafana + exportación diaria.
5. Servicio de visión cenital + calibración de zonas.
6. Reclamos y auditoría.

Proyecto relacionado (fuera de alcance): trazabilidad de paquetes con QR entre procesos; puede alimentar el conteo de piezas.
