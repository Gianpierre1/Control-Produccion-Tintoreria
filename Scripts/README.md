# Scripts

Código Python utilizado para:

- Conexión con SQL Server
- Extracción de datos
- Análisis de producción
- Generación de indicadores

## costura/

Sistema de tiempos improductivos en Costura:

- `schema.sql`: esquema PostgreSQL + TimescaleDB (sin validar contra un servidor todavía).
- `formulas.py`: fórmulas oficiales de eficiencia.
- `schema_app.sql`: tablas de la app de tablet (órdenes, tickets, dispositivos, eventos).
- `segmentos.py`: minutos del día a partir de los eventos de la tablet.
- `tickets.py`: códigos de ticket con dígito de control y división en paquetes.
- `tests/`: ejecutar con `python3 -m pytest Scripts/costura/tests`.
