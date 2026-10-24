-- Esquema de la app de tablet (Documentación/costura/03-app-tablet.md).
-- Se aplica sobre schema.sql: reutiliza operaria, puesto, operacion, causa, parada,
-- resumen_diario, reclamo y auditoria. Las tablas de sensores (lectura_maquina,
-- evento_vision) no son necesarias en este enfoque.

-- Copias sincronizadas desde SQL Server (solo lectura desde el servidor).
CREATE TABLE orden_produccion (
    id            serial PRIMARY KEY,
    codigo_erp    text NOT NULL UNIQUE,
    estilo        text NOT NULL,
    cliente       text,
    sincronizada  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ruta_operacion (
    id            serial PRIMARY KEY,
    orden_id      int  NOT NULL REFERENCES orden_produccion(id),
    secuencia     int  NOT NULL,
    operacion_id  int  NOT NULL REFERENCES operacion(id),
    UNIQUE (orden_id, secuencia)
);

-- Tickets generados por el sistema.
CREATE SEQUENCE ticket_seq;

CREATE TABLE ticket (
    id                 bigserial PRIMARY KEY,
    codigo             text        NOT NULL UNIQUE,      -- T + 8 dígitos + control
    orden_id           int         NOT NULL REFERENCES orden_produccion(id),
    color              text        NOT NULL,
    talla              text        NOT NULL,
    cantidad           integer     NOT NULL CHECK (cantidad > 0),
    ticket_origen_id   bigint      REFERENCES ticket(id), -- reproceso
    estado             text        NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo', 'anulado')),
    creado             timestamptz NOT NULL DEFAULT now(),
    creado_por         text        NOT NULL
);

-- Ruta copiada al emitir el ticket: los cambios posteriores del ERP no la alteran.
CREATE TABLE ticket_operacion (
    id            bigserial PRIMARY KEY,
    ticket_id     bigint  NOT NULL REFERENCES ticket(id),
    secuencia     int     NOT NULL,
    operacion_id  int     NOT NULL REFERENCES operacion(id),
    smv           numeric NOT NULL CHECK (smv > 0),
    UNIQUE (ticket_id, secuencia)
);

CREATE TABLE dispositivo (
    id          serial PRIMARY KEY,
    nombre      text NOT NULL,
    token_hash  text NOT NULL,
    puesto_id   int  REFERENCES puesto(id),
    estado      text NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'aprobado', 'bloqueado')),
    creado      timestamptz NOT NULL DEFAULT now()
);

-- Eventos enviados por la tablet. Inmutables; idempotentes por event_id.
CREATE TABLE evento_tablet (
    event_id              uuid PRIMARY KEY,
    operaria_id           int         NOT NULL REFERENCES operaria(id),
    dispositivo_id        int         NOT NULL REFERENCES dispositivo(id),
    puesto_id             int         REFERENCES puesto(id),
    tipo                  text        NOT NULL CHECK (tipo IN (
        'JORNADA_INICIO', 'JORNADA_FIN', 'DESCANSO_INICIO', 'DESCANSO_FIN',
        'OP_INICIO', 'OP_FIN', 'PARADA_INICIO', 'PARADA_FIN')),
    ts_tablet             timestamptz NOT NULL,           -- hora declarada por la tablet
    ts_servidor           timestamptz NOT NULL DEFAULT now(),
    desfase_reloj_s       real,                           -- tablet vs servidor al enviar
    ticket_operacion_id   bigint      REFERENCES ticket_operacion(id),
    causa_codigo          text        REFERENCES causa(codigo),
    piezas                integer     CHECK (piezas >= 0)
);
CREATE INDEX ON evento_tablet (operaria_id, ts_tablet);
CREATE INDEX ON evento_tablet (ticket_operacion_id);
