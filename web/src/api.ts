import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "react-oidc-context";
import type { Alert, Band, EngineDetail, EngineSummary, PipelineStatus } from "./types";

const REFRESH_MS = 3000;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function useFetcher() {
  const auth = useAuth();
  const token = auth.user?.access_token;
  return async <T,>(path: string, init?: RequestInit): Promise<T> => {
    const res = await fetch(path, {
      ...init,
      headers: { ...(init?.headers ?? {}), Authorization: `Bearer ${token}`, Accept: "application/json" },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(res.status, body.detail ?? res.statusText);
    }
    return res.json() as Promise<T>;
  };
}

export function useEngines(band?: Band) {
  const get = useFetcher();
  const qs = band ? `?band=${band}` : "";
  return useQuery({
    queryKey: ["engines", band ?? "all"],
    queryFn: () => get<EngineSummary[]>(`/api/engines${qs}`),
    refetchInterval: REFRESH_MS,
  });
}

export function useEngine(id: number) {
  const get = useFetcher();
  return useQuery({
    queryKey: ["engine", id],
    queryFn: () => get<EngineDetail>(`/api/engines/${id}`),
    refetchInterval: REFRESH_MS,
  });
}

export function useAlerts(status: "open" | "acknowledged" | "all") {
  const get = useFetcher();
  return useQuery({
    queryKey: ["alerts", status],
    queryFn: () => get<Alert[]>(`/api/alerts?status=${status}`),
    refetchInterval: REFRESH_MS,
  });
}

export function usePipeline() {
  const get = useFetcher();
  return useQuery({
    queryKey: ["pipeline"],
    queryFn: () => get<PipelineStatus>("/api/pipeline"),
    refetchInterval: REFRESH_MS,
  });
}

export function useAcknowledge() {
  const get = useFetcher();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => get<Alert>(`/api/alerts/${id}/acknowledge`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["engine"] });
      qc.invalidateQueries({ queryKey: ["pipeline"] });
    },
  });
}
