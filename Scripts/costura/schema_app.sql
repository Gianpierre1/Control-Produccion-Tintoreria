-- Esquema de la app de tablet (Documentación/costura/03-app-tablet.md).
-- Se aplica sobre schema.sql: reutiliza operaria, puesto, operacion, reclamo y auditoria.
-- No se usan en este enfoque: lectura_maquina, evento_vision, causa, parada ni resumen_diario
-- (no hay minutos improductivos; la eficiencia se calcula por operación).

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

-- Motivos de pausa: cada uno tiene un tiempo permitido para volver.
CREATE TABLE motivo_pausa (
    codigo       text PRIMARY KEY,
    descripcion  text    NOT NULL,
    limite_min   numeric NOT NULL CHECK (limite_min >= 0)
);

-- Eventos enviados por la tablet. Inmutables; idempotentes por event_id.
CREATE TABLE evento_tablet (
    event_id              uuid PRIMARY KEY,
    operaria_id           int         NOT NULL REFERENCES operaria(id),
    dispositivo_id        int         NOT NULL REFERENCES dispositivo(id),
    puesto_id             int         REFERENCES puesto(id),
    tipo                  text        NOT NULL CHECK (tipo IN (
        'JORNADA_INICIO', 'JORNADA_FIN', 'OP_INICIO', 'OP_FIN', 'PAUSA_INICIO', 'PAUSA_FIN')),
    ts_tablet             timestamptz NOT NULL,           -- hora declarada por la tablet
    ts_servidor           timestamptz NOT NULL DEFAULT now(),
    desfase_reloj_s       real,                           -- tablet vs servidor al enviar
    ticket_operacion_id   bigint      REFERENCES ticket_operacion(id),
    motivo_codigo         text        REFERENCES motivo_pausa(codigo),
    piezas                integer     CHECK (piezas >= 0)
);
CREATE INDEX ON evento_tablet (operaria_id, ts_tablet);
CREATE INDEX ON evento_tablet (ticket_operacion_id);

-- Resultado calculado por operación terminada (se recalcula desde los eventos).
CREATE TABLE resultado_operacion (
    ticket_operacion_id  bigint  PRIMARY KEY REFERENCES ticket_operacion(id),
    operaria_id          int     NOT NULL REFERENCES operaria(id),
    inicio               timestamptz NOT NULL,
    fin                  timestamptz NOT NULL,
    piezas               integer NOT NULL,
    min_transcurridos    numeric NOT NULL,
    min_pausa_permitida  numeric NOT NULL,
    min_pausa_exceso     numeric NOT NULL,
    min_real             numeric NOT NULL,
    min_asignado         numeric NOT NULL,
    eficiencia           numeric
);
