export type Band = "healthy" | "warning" | "critical";

export interface EngineSummary {
  engine_id: number;
  cycle: number;
  rul_pred: number;
  band: Band;
  model_version: string;
  scored_at: string;
}

export interface Alert {
  id: number;
  engine_id: number;
  band: Exclude<Band, "healthy">;
  cycle: number;
  rul_pred: number;
  raised_at: string;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}

export interface EngineDetail {
  engine_id: number;
  predictions: { cycle: number; rul_pred: number; band: Band }[];
  readings: ({ cycle: number } & Record<string, number>)[];
  alerts: Alert[];
}

export interface PartitionStatus {
  partition: number;
  committed_offset: number;
  end_offset: number;
  lag: number;
  owner: string | null;
}

export interface PipelineStatus {
  database: {
    readings: number;
    predictions: number;
    dead_letters: number;
    open_alerts: number;
    last_ingested_at: string | null;
  };
  kafka:
    | { topic: string; group: string; state: string; partitions: PartitionStatus[]; total_lag: number }
    | { error: string };
  dead_letters: {
    id: number;
    kafka_partition: number;
    kafka_offset: number;
    error: string;
    payload: string;
    received_at: string;
  }[];
}
