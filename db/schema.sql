-- Fleet health schema. Idempotent: safe to run on every start.
-- Natural keys (engine_id, cycle) make every write an upsert, so Kafka redelivery cannot create duplicates.

CREATE TABLE IF NOT EXISTS readings (
    engine_id       integer          NOT NULL,
    cycle           integer          NOT NULL,
    op_setting_1    double precision NOT NULL,
    op_setting_2    double precision NOT NULL,
    op_setting_3    double precision NOT NULL,
    s1  double precision NOT NULL, s2  double precision NOT NULL, s3  double precision NOT NULL,
    s4  double precision NOT NULL, s5  double precision NOT NULL, s6  double precision NOT NULL,
    s7  double precision NOT NULL, s8  double precision NOT NULL, s9  double precision NOT NULL,
    s10 double precision NOT NULL, s11 double precision NOT NULL, s12 double precision NOT NULL,
    s13 double precision NOT NULL, s14 double precision NOT NULL, s15 double precision NOT NULL,
    s16 double precision NOT NULL, s17 double precision NOT NULL, s18 double precision NOT NULL,
    s19 double precision NOT NULL, s20 double precision NOT NULL, s21 double precision NOT NULL,
    event_id        uuid             NOT NULL,
    produced_at     timestamptz      NOT NULL,
    kafka_partition integer          NOT NULL,
    kafka_offset    bigint           NOT NULL,
    ingested_at     timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (engine_id, cycle)
);

CREATE TABLE IF NOT EXISTS predictions (
    engine_id     integer          NOT NULL,
    cycle         integer          NOT NULL,
    rul_pred      double precision NOT NULL,
    band          text             NOT NULL CHECK (band IN ('healthy', 'warning', 'critical')),
    model_version text             NOT NULL,
    scored_at     timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (engine_id, cycle)
);

-- One alert per engine per band: a redelivered message re-raises nothing.
CREATE TABLE IF NOT EXISTS alerts (
    id              bigserial PRIMARY KEY,
    engine_id       integer          NOT NULL,
    band            text             NOT NULL CHECK (band IN ('warning', 'critical')),
    cycle           integer          NOT NULL,
    rul_pred        double precision NOT NULL,
    raised_at       timestamptz      NOT NULL DEFAULT now(),
    acknowledged_by text,
    acknowledged_at timestamptz,
    UNIQUE (engine_id, band)
);

CREATE TABLE IF NOT EXISTS dead_letters (
    id              bigserial PRIMARY KEY,
    topic           text        NOT NULL,
    kafka_partition integer     NOT NULL,
    kafka_offset    bigint      NOT NULL,
    error           text        NOT NULL,
    payload         text        NOT NULL,
    received_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (topic, kafka_partition, kafka_offset)
);

CREATE INDEX IF NOT EXISTS predictions_latest ON predictions (engine_id, cycle DESC);
