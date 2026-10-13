# Integración, red y distribución

Supuestos (confirmar en planta): ~100 cámaras, 4 puestos por cámara → ~400 puestos; ~16 líneas de ~25 máquinas → ~6–7 cámaras por línea. Las cámaras van en la estructura de las luminarias, mirando hacia abajo.

## 1. Aclaración: switch PoE vs AP

- **Las cámaras necesitan un switch PoE.** Un AP (punto de acceso) es otro equipo: solo da WiFi. No alimenta ni conecta cámaras con cable.
- Los **AP sí hacen falta** para los nodos de máquina (ESP32 por WiFi). Cada AP también se alimenta por PoE desde esos mismos switches.
- Un switch PoE de 24 puertos puede alimentar cámaras **y** AP.

## 2. Esquema general

```
                         ┌─────────────────────────┐
                         │ Servidor (GPU)          │
                         │ Mosquitto · BD · Visión │
                         └───────────┬─────────────┘
                                     │ 1 GbE (o 10 GbE SFP+)
                         ┌───────────┴─────────────┐
                         │ Switch núcleo (sala     │
                         │ de servidores)          │
                         └─┬────┬────┬────┬────┬───┘
            fibra/UTP SFP  │    │    │    │    │   (uno por zona)
                  ┌────────┘    │    │    │    └────────┐
            ┌─────┴────┐  ┌─────┴──┐ ...            ┌────┴─────┐
            │ SW PoE 1 │  │SW PoE 2│                │ SW PoE 6 │   gabinetes
            │ 24 pts   │  │ 24 pts │                │ 24 pts   │   en planta
            └─┬─┬─┬─┬──┘  └────────┘                └──────────┘
              │ │ │ └─ AP WiFi (PoE) ── ESP32 de máquina (WiFi 2.4 GHz)
              │ │ └─── Cámara ESP32-S3 (luminaria) ─ cubre 4 puestos
              │ └───── Cámara ...
              └─────── Cámara ... (hasta ~20 por switch)
```

- **Topología en árbol:** servidor → núcleo → switches PoE por zona → cámaras. Sin hubs ni splitters pasivos.
- **Distancia:** máx. 100 m de cable por cámara (canal permanente ≤ 90 m). Entre gabinetes, fibra o UTP con SFP.
- **Cada cámara tiene su cable propio**, no se encadenan cámaras.

## 3. Distribución de switches (~100 cámaras)

Por switch: ~17–20 cámaras + 1–2 AP + 2–3 puertos de reserva.

| Switch | Líneas (supuesto) | Cámaras | AP | Puertos usados / 24 |
|---|---|---|---|---|
| SW-PoE-1 | 1–3 | ~19 | 2 | 21 |
| SW-PoE-2 | 4–6 | ~19 | 2 | 21 |
| SW-PoE-3 | 7–9 | ~19 | 2 | 21 |
| SW-PoE-4 | 10–12 | ~19 | 2 | 21 |
| SW-PoE-5 | 13–15 | ~19 | 2 | 21 |
| SW-PoE-6 | 16 | ~6 | 1 | 7 (crecimiento) |
| **Total** | | **~101** | **11** | |

**Consumo PoE:** 20 cámaras × 6 W + 2 AP × 15 W ≈ **150 W por switch**, frente a 384 W disponibles (TL-SG3428MP). Hay holgura para cámaras IP más pesadas si luego se cambia a Plan C estándar (~7–10 W).

**Gabinetes:** un gabinete por cada 3 líneas, a media altura de la nave o en la pared lateral, de modo que el tramo más largo hasta la última cámara quede por debajo de 90 m. Plano real pendiente: medir distancias antes de fijar posiciones.

**Piloto:** 1 línea → 7 cámaras + 1–2 AP → **un solo switch PoE de 24 puertos**. Todo lo demás se agrega después con el mismo diseño.

## 4. VLAN y direccionamiento

| VLAN | Uso | Subred | Quién |
|---|---|---|---|
| 10 | Gestión (switches, AP) | 10.10.10.0/24 | TI / Ingeniería |
| 20 | Cámaras (ESP32-CAM, IP) | 10.10.20.0/23 | Solo hacia el servidor |
| 30 | Nodos de máquina (ESP32 WiFi/Ethernet) | 10.10.30.0/23 | Solo hacia Mosquitto |
| 40 | Servidor y tableros | 10.10.40.0/24 | Supervisión, Ingeniería |

- Reglas: las VLAN 20 y 30 solo hablan con el servidor (MQTT 1883/8883, HTTP de captura). Sin acceso a internet ni a la red corporativa.
- IP fija o reserva DHCP por dispositivo; nombre = `linea-puesto` o `cam-linea-zona`.
- NTP local en el servidor para que todos los nodos compartan hora.
- Mosquitto con usuario y contraseña por tipo de nodo (TLS recomendado).

## 5. Flujo de datos y ancho de banda

| Flujo | Origen → destino | Carga |
|---|---|---|
| Telemetría de máquina | ESP32 de máquina → MQTT | ~200 B/s por nodo → ~80 kB/s en total |
| Eventos de botones | ESP32 → MQTT | Despreciable |
| Imagen de cámara | Cámara ESP32-S3 → servidor (HTTP o MQTT) | 1280×720 JPEG ≈ 60–120 kB; a 2 fps ≈ 1–2 Mbps por cámara |
| Eventos de visión | Servidor → MQTT interno | Despreciable |

Las 100 cámaras a 2 fps suman ~100–200 Mbps hacia el servidor; cada switch solo agrega ~20–40 Mbps. Con uplinks de 1 Gbps hay amplio margen.

**Ahorro de proceso:** el servidor **solo pide la foto cuando el nodo de máquina del puesto reporta "no cosiendo"**. Si la máquina cose, no hace falta mirar. Eso baja la carga de GPU y de red a una fracción.

## 6. Cómo la cámara de la luminaria cubre 4 puestos

1. Cámara en el centro de un grupo de 4 puestos, a la altura de la luminaria, apuntando hacia abajo.
2. Zonas poligonales por puesto en el servidor (archivo de configuración por cámara).
3. Modelo de pose (RTMPose / MediaPipe) busca persona y muñecas dentro de cada zona.
4. Regla de movimiento (sección 5.2 del brief) → trabajando / inactiva / ausente.

**Riesgos a validar en el prototipo (semanas 2–4):**
- Altura de las luminarias y ángulo del lente: si el campo de visión es muy cerrado, no entran 4 puestos.
- Desde arriba, las muñecas se ven pequeñas o tapadas por la cabeza y los hombros.
- La iluminación (luminarias LED con parpadeo) puede introducir bandas en la imagen del OV5640.
- Resolución real útil: 2592 px sobre ~6 m de ancho ≈ 430 px/m; suficiente para presencia y movimiento grueso, justa para movimiento de dedos.
- Si falla, hay dos salidas: cámara IP 4 MP por cada 4–6 puestos (Hikvision DS-2CD2143G2-I) o Plan B (una cámara más cerca de cada puesto).

## 7. Opciones para conectar los nodos de máquina (ESP32)

El diseño base es **WiFi 2.4 GHz con AP en el techo**. Si la planta tiene mucho ruido o se quiere más robustez:

| Opción | Cómo funciona | Ventajas | Desventajas | Cuándo usarla |
|---|---|---|---|---|
| **1. WiFi (base)** | ESP32 → AP PoE → switch | Sin cables hasta el puesto; barato | 400 clientes → 8–10 AP con canales 1/6/11 y potencia baja; interferencia | Piloto y planta completa |
| **2. Ethernet + PoE** | ESP32-S3-ETH (o Olimex ESP32-POE-ISO) → cable al switch | La conexión más estable; PoE da alimentación | Un cable y un puerto por puesto (~400 puertos más) | Puestos con mala señal |
| **3. Bus RS-485 / Modbus** | Varios ESP32 por línea en un bus de 2 hilos hacia una pasarela | Pocos cables, inmune al ruido | Hay que desarrollar protocolo y pasarela | Si el WiFi falla en una nave |
| **4. ESP-NOW / malla** | Los ESP32 se hablan entre sí y un ESP32 pasarela entra a la red | Sin AP, baja latencia | Cobertura y depuración más complicadas | Pruebas o zonas sin AP |
| **5. Un nodo por 2 máquinas** | Un ESP32 con 2 pinzas ADS1115 (4 canales) | Menos nodos y menos dispositivos en WiFi | Si el nodo falla se pierden 2 puestos | Reduce de 400 a ~200 clientes |

**Recomendación:** WiFi en el piloto; medir pérdida de paquetes y latencia. Si en alguna zona supera 1–2 %, pasar esa zona a la opción 2 (Ethernet + PoE) o a la opción 5.

## 8. Opciones para los botones de causa

| Opción | Descripción | Ventajas | Desventajas |
|---|---|---|---|
| **1. Botonera cableada (base)** | 4 pulsadores luminosos en el nodo de máquina: Material, Máquina, Reproceso, Otro | Confiable, rápida, sin batería | Cable corto; la operaria debe alcanzarla |
| **2. Botones inalámbricos** | Botones BLE o Zigbee que cuelgan en cada puesto | Sin cable; reubicables | Pilas; emparejamiento; más puntos de falla |
| **3. Tablet del supervisor** | Lista de puestos parados; el supervisor elige la causa | Una sola interfaz por línea | Depende de que el supervisor la use a tiempo |
| **4. Registro del mecánico / habilitador** | El mecánico o el habilitador marca "atendiendo" y la causa al llegar al puesto | La causa la declara quien la conoce | Requiere botón o teléfono por rol |
| **5. Lector QR de causa** | El mecánico escanea un QR al llegar y otro al terminar | Registra tiempos de atención | Más pasos |

**Recomendación:** botonera cableada (1) + tablet del supervisor (3) como respaldo + registro del mecánico (4), que cubre la causa "Máquina" con tiempos de atención reales. Esto sigue el principio del brief: la causa no recae solo en la operaria.

## 9. Orden de instalación del piloto

1. Medir altura de luminarias y plano de la línea piloto; definir ubicación de gabinete y AP.
2. Tender los cables Cat6 a cada posición de cámara; certificar.
3. Instalar el switch PoE y configurar VLAN, NTP y Mosquitto.
4. Montar 2 cámaras de prueba (con lente gran angular) y grabar un día completo **solo para calibrar**.
5. Montar los nodos de máquina de la línea y calibrar la pinza de cada modelo de motor.
6. Comparar contra el estudio de tiempos manual (semanas 1–2) antes de decidir.

## 10. Cámaras arriba, botones abajo

La cámara va en la luminaria y solo recibe PoE. Los botones de causa y la pinza de corriente van en el **nodo del puesto**, al alcance de la operaria. Rutas para que el dato llegue a MQTT:

| Ruta | Cómo funciona | Ventajas | Riesgos |
|---|---|---|---|
| **A. WiFi al AP (base)** | Nodo del puesto (botones + pinza) → WiFi 2.4 GHz → AP PoE → switch. La cámara va aparte por PoE | Independiente de la cámara; ya descrito en la sección 7 | ~400 clientes WiFi; 8–10 AP |
| **B. ESP-NOW hacia la cámara** | Nodo del puesto → ESP-NOW → cámara ESP32-S3 de arriba (4 puestos) → cable PoE → MQTT | Sin APs ni WiFi de planta; los botones pueden ir a pila | Firmware propio; cobertura con estructura metálica a medir; probar ESP-NOW + Ethernet juntos en el ESP32-S3 |
| **C. Cable por la columna** | UTP desde la estructura hasta una caja en la mesa | La conexión más confiable | Obra y un cable por puesto |
| **D. Botonera inalámbrica + nodo con pinza cableado** | Botones a pila por ESP-NOW a la cámara; la pinza en un nodo con alimentación | Botones reubicables sin cable | Pilas y emparejamiento |

**Piloto:** probar A y B en la misma línea, con puestos repartidos en cada ruta. Medir pérdida de paquetes y latencia de los botones. Si B no es fiable, se mantiene A sin cambiar nada más.
