# Hardware: modelos concretos y cantidades

> **Estado de verificación.** Marqué cada modelo así:
> ✅ confirmado con ficha o tienda en búsqueda web (octubre 2026) · ⚠️ lo recomiendo de memoria; **confirmar ficha técnica y stock en Perú antes de comprar**.
> Los precios no están aquí: cotizar en Perú (los rangos USD de la presentación son orientativos).

## 1. Nodo de cámara (piloto): ESP32-S3 con PoE en las luminarias

| Ítem | Modelo | Estado | Notas |
|---|---|---|---|
| Placa + cámara + PoE | **Waveshare ESP32-S3-POE-ETH-M-CAM-KIT** | ✅ | ESP32-S3 dual-core 240 MHz, WiFi 2.4 GHz, Ethernet 10/100, módulo PoE, cámara OV5640 (5 MP, 2592×1944). El kit "M" trae los pines soldados. Un listado indica PoE IEEE 802.3af/at: **confirmar en la wiki de Waveshare** |
| Lente gran angular | Lente OV5640 de 120°–160° con conector DVP de 24 pines | ⚠️ | El lente de serie es angosto. **Sin gran angular no cubrirá 4 puestos.** Pedir 1 unidad de prueba antes de comprar 100 |
| Soporte | Caja IP54 o soporte impreso 3D que sujete la placa al perfil de la luminaria | — | Cámara mirando hacia abajo, sin cables colgando |
| Cable | UTP Cat5e/Cat6 exterior de la canaleta al switch, con conector RJ-45 en la placa | — | ≤ 100 m por tramo |

**Qué puede y qué no puede hacer este nodo:**
- Sí: capturar JPEG (p. ej. 1280×720 o 1600×1200) y enviarlo por HTTP/MQTT al servidor, cuando el servidor lo pida o cada N segundos.
- No: correr el modelo de pose ni hacer streaming RTSP estable a 5 fps con 4 MP. **La pose se calcula en el servidor.**
- El mismo nodo puede publicar su propia telemetría (Wi-Fi/Ethernet, temperatura, versión de firmware).

**Consumo PoE:** estimado 2–4 W en la placa; reservar **6 W por puerto** hasta medirlo en el prototipo.

**Alternativa si el OV5640 no rinde (Plan C estándar):**

| Ítem | Modelo | Estado | Notas |
|---|---|---|---|
| Cámara IP cenital 4 MP | **Hikvision DS-2CD2143G2-I** (lente 2.8 mm, 103° horizontal) | ✅ | 2688×1520, PoE 802.3af, ONVIF, RTSP, H.265. Se vende como "IP67/IK10" (sobrado para interior) |

## 2. Nodo de máquina (uno por puesto)

| Ítem | Modelo | Estado | Notas |
|---|---|---|---|
| Microcontrolador (WiFi) | **Espressif ESP32-S3-DevKitC-1** (N8R2 o N8) | ⚠️ | Opción base. WiFi 2.4 GHz |
| Microcontrolador (cable) | **Waveshare ESP32-S3-ETH** (+ módulo PoE) | ✅ | Misma familia que el nodo de cámara: un solo firmware base |
| Alternativa cable | Olimex ESP32-POE-ISO | ⚠️ | Ethernet + PoE aislado; más caro |
| Sensor de corriente | **YHDC SCT-013-005** (5 A : 1 V, salida en tensión) | ⚠️ | Para motores de costura (~2–3 A típicos). Si el motor pasa de 5 A, usar la -010 |
| Convertidor ADC | **ADS1115** (módulo I²C, 16 bits) | ⚠️ | El ADC interno del ESP32 es poco lineal; este da mejor resolución para Irms |
| Circuito de lectura | Divisor de polarización 2 × 10 kΩ + condensador 10 µF + diodos de protección | — | Para centrar la señal CA en 1.65 V |
| Radar de presencia (opcional) | **Hi-Link HLK-LD2410C** | ✅ | UART a 256000 baudios (8N1), 5 V de alimentación. Salida OUT digital y datos por UART. Verificar nivel lógico 3.3 V |
| Botonera de causas | 4 pulsadores luminosos de 16 mm (Material, Máquina, Reproceso, Otro) + caja ABS | — | Cableados a GPIO con resistencia pull-up. Un color por causa |
| Fuente | Fuente 5 V / 2 A por nodo (o PoE en la versión cableada) | — | |
| Caja | Caja ABS IP54 con prensaestopas | — | Fijada a la mesa, lejos de la banda de la máquina |

**Seguridad eléctrica:** la pinza se instala **abrazando un solo conductor** (fase) del cable de la máquina, con un cable en Y o adaptador. La instala un electricista, con la máquina apagada. No se abre la carcasa del motor.

## 3. Red

| Ítem | Modelo | Estado | Notas |
|---|---|---|---|
| Switch PoE de acceso (24 puertos) | **TP-Link TL-SG3428MP** (24× PoE+ gigabit, presupuesto 384 W, 4× SFP, VLAN 802.1Q, SNMP) | ✅ | La versión v1 figura EOL en EE. UU.; **verificar disponibilidad en Perú**. Con 24 cámaras a 6 W solo se usan ~150 W: sobrado |
| Alternativa | **Ubiquiti UniFi USW-Pro-Max-24-PoE** (400 W, 16× GbE + 8× 2.5 GbE, 2× SFP+) | ✅ | Más caro; útil si se prefiere el ecosistema UniFi. Un listado se contradice en el PoE por puerto del USW-Pro-24-PoE: validar en la ficha oficial |
| Switch núcleo / agregación | Switch L2 gestionable con puertos SFP/SFP+ (p. ej. TP-Link TL-SG3428 o TL-SG3210XHP-M2) | ⚠️ | Solo agrega los uplinks de los switches PoE y el servidor. No necesita PoE |
| Punto de acceso WiFi (nodos de máquina) | **TP-Link Omada EAP610** o **Ubiquiti UniFi U6-Pro** | ⚠️ | Techo, alimentado por PoE desde los switches de acceso. Los ESP32 solo usan 2.4 GHz |
| Cable | UTP Cat6 (o Cat5e) LSZH, certificado, ≤ 90 m de canal permanente | — | Un cable por cámara desde el gabinete de la zona |
| Fibra / SFP | Módulos SFP 1G (LC, multimodo) entre gabinetes | ⚠️ | Si las distancias entre gabinetes pasan de 100 m |
| Gabinetes | Gabinete mural 6U–9U por zona, con patch panel, PDU y ventilación | — | |
| UPS | UPS de 1–3 kVA por gabinete, más UPS en el servidor | — | La caída de energía no debe cortar el registro |

## 4. Servidor

| Ítem | Especificación | Notas |
|---|---|---|
| CPU | 8 núcleos o más (Ryzen 7 / Core i7) | |
| GPU | NVIDIA RTX 4060 de 8 GB mínimo; **RTX 4060 Ti de 16 GB recomendada** si se procesan 100 cámaras | ⚠️ Capacidad real a medir en el piloto |
| RAM | 32 GB | |
| Disco | NVMe 1 TB (base de datos) + 2 TB (fotos de paradas en disputa, 30 días) | |
| SO | Ubuntu Server 24.04 LTS | Sugerido |
| Software | Mosquitto, PostgreSQL + TimescaleDB, Grafana, servicios Python | Todo local |

Las especificaciones se afinan tras el piloto, cuando se mida cuántos cuadros por segundo procesa realmente la GPU.

## 5. Cantidades

### Piloto (1 línea de 25 máquinas, 4 puestos por cámara)

| Ítem | Cantidad |
|---|---|
| Nodos de cámara Waveshare ESP32-S3-POE-ETH-M-CAM-KIT | 7 + 1 de repuesto |
| Lentes gran angular para prueba | 2 |
| Cámara Hikvision DS-2CD2143G2-I (comparación, plan alterno) | 1 |
| Nodos de máquina (ESP32 + SCT-013-005 + ADS1115 + botonera) | 25 + 3 de repuesto |
| Radares LD2410C | 5 (solo para comparar con la cámara) |
| Switch PoE de 24 puertos | 1 |
| Punto de acceso WiFi | 1–2 |
| Servidor | 1 |

### Planta completa (~100 cámaras, ~400 puestos)

| Ítem | Cantidad |
|---|---|
| Nodos de cámara | 100 + 5 % de repuesto |
| Nodos de máquina | ~400 + 5 % de repuesto |
| Switches PoE de 24 puertos | 6 (ver 02-integracion-y-red.md) |
| Switch núcleo | 1 |
| Puntos de acceso WiFi | 8–10 |
| Servidor con GPU | 1 (+ 1 de respaldo en frío) |

> Estas cantidades parten de **25 máquinas por línea** (supuesto de la presentación). Confirmar con el número real de líneas y puestos.
