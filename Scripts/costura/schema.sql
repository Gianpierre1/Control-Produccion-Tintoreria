-- Esquema mínimo: medición de tiempos improductivos en Costura.
-- PostgreSQL + TimescaleDB. Ver Documentación/costura/00-brief-tecnico.md (sección 5.3).

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE linea (
    id      serial PRIMARY KEY,
    nombre  text NOT NULL UNIQUE
);

CREATE TABLE puesto (
    id            serial PRIMARY KEY,
    linea_id      int  NOT NULL REFERENCES linea(id),
    maquina       text NOT NULL,
    camara_id     text,
    zona_poligono jsonb,                       -- polígono del puesto en la imagen de la cámara
    UNIQUE (linea_id, maquina)
);

CREATE TABLE operaria (
    id      serial PRIMARY KEY,
    nombre  text NOT NULL
);

CREATE TABLE asignacion_turno (
    id           serial PRIMARY KEY,
    operaria_id  int         NOT NULL REFERENCES operaria(id),
    puesto_id    int         NOT NULL REFERENCES puesto(id),
    inicio       timestamptz NOT NULL,
    fin          timestamptz NOT NULL,
    CHECK (fin > inicio)
);
CREATE INDEX ON asignacion_turno (puesto_id, inicio, fin);
CREATE INDEX ON asignacion_turno (operaria_id, inicio);

CREATE TABLE operacion (
    id      serial PRIMARY KEY,
    nombre  text    NOT NULL,
    smv     numeric NOT NULL CHECK (smv > 0)   -- minutos estándar por pieza
);

CREATE TABLE asignacion_operacion (
    id            serial PRIMARY KEY,
    puesto_id     int         NOT NULL REFERENCES puesto(id),
    operacion_id  int         NOT NULL REFERENCES operacion(id),
    inicio        timestamptz NOT NULL,
    fin           timestamptz NOT NULL,
    CHECK (fin > inicio)
);

CREATE TABLE lectura_maquina (
    puesto_id  int         NOT NULL REFERENCES puesto(id),
    ts         timestamptz NOT NULL,
    estado     text        NOT NULL CHECK (estado IN ('cosiendo', 'encendida', 'apagada')),
    irms       real
);
SELECT create_hypertable('lectura_maquina', 'ts');
CREATE INDEX ON lectura_maquina (puesto_id, ts DESC);

CREATE TABLE evento_vision (
    id         bigserial PRIMARY KEY,
    puesto_id  int         NOT NULL REFERENCES puesto(id),
    inicio     timestamptz NOT NULL,
    fin        timestamptz NOT NULL,
    estado     text        NOT NULL CHECK (estado IN ('trabajando', 'inactiva', 'ausente')),
    confianza  real        CHECK (confianza BETWEEN 0 AND 1),
    CHECK (fin > inicio)
);
CREATE INDEX ON evento_vision (puesto_id, inicio);

CREATE TABLE causa (
    codigo       text PRIMARY KEY,             -- MAT | MAQ | REP | OTR ...
    descripcion  text NOT NULL,
    compensable  boolean NOT NULL              -- [ABIERTO] política de qué se descuenta
);

CREATE TABLE parada (
    id                 bigserial PRIMARY KEY,
    puesto_id          int         NOT NULL REFERENCES puesto(id),
    inicio             timestamptz NOT NULL,
    fin                timestamptz NOT NULL,
    causa_codigo       text        REFERENCES causa(codigo),   -- NULL = parada sin causa
    fuente             text        NOT NULL CHECK (fuente IN ('boton', 'supervisor', 'mecanico', 'vision', 'reclamo')),
    registrada_por     text,
    estado_validacion  text        NOT NULL DEFAULT 'pendiente'
                       CHECK (estado_validacion IN ('pendiente', 'validada', 'rechazada')),
    CHECK (fin > inicio)
);
CREATE INDEX ON parada (puesto_id, inicio);

CREATE TABLE produccion (
    id            bigserial PRIMARY KEY,
    operaria_id   int     NOT NULL REFERENCES operaria(id),
    operacion_id  int     NOT NULL REFERENCES operacion(id),
    fecha         date    NOT NULL,
    piezas        integer NOT NULL CHECK (piezas >= 0),
    fuente        text    NOT NULL CHECK (fuente IN ('erp', 'ticket', 'estimado'))
);
CREATE INDEX ON produccion (operaria_id, fecha);

CREATE TABLE resumen_diario (
    operaria_id          int     NOT NULL REFERENCES operaria(id),
    fecha                date    NOT NULL,
    min_estandar         numeric NOT NULL,
    min_trabajados       numeric NOT NULL,
    min_improductivos    numeric NOT NULL,
    ef_real              numeric,
    ef_compensada        numeric,
    pct_improductivo     numeric,
    PRIMARY KEY (operaria_id, fecha)
);

CREATE TABLE reclamo (
    id            bigserial PRIMARY KEY,
    parada_id     bigint      NOT NULL REFERENCES parada(id),
    solicitante   text        NOT NULL,
    motivo        text        NOT NULL,
    estado        text        NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto', 'aceptado', 'rechazado')),
    resuelto_por  text,
    ts            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE auditoria (
    id              bigserial PRIMARY KEY,
    tabla           text        NOT NULL,
    registro_id     text        NOT NULL,
    campo           text        NOT NULL,
    valor_anterior  text,
    valor_nuevo     text,
    usuario         text        NOT NULL,
    ts              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON auditoria (tabla, registro_id);

-- Causas iniciales (catálogo [ABIERTO]: confirmar cuáles son compensables).
INSERT INTO causa (codigo, descripcion, compensable) VALUES
    ('MAT', 'Espera de material',  true),
    ('MAQ', 'Falla de máquina',    true),
    ('REP', 'Reproceso',           false),
    ('OTR', 'Otro',                false);
