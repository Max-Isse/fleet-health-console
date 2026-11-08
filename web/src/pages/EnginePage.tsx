import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useAcknowledge, useEngine } from "../api";
import { useRoles } from "../auth";
import AlertsTable from "../components/AlertsTable";
import BandBadge from "../components/BandBadge";

// Sensor names from the C-MAPSS documentation, for the sensors the model uses.
const SENSOR_LABELS: Record<string, string> = {
  s2: "s2 · LPC outlet temperature (°R)",
  s3: "s3 · HPC outlet temperature (°R)",
  s4: "s4 · LPT outlet temperature (°R)",
  s7: "s7 · HPC outlet pressure (psia)",
  s11: "s11 · HPC outlet static pressure (psia)",
  s12: "s12 · fuel flow / Ps30 ratio",
  s15: "s15 · bypass ratio",
  s17: "s17 · bleed enthalpy",
  s20: "s20 · HPT coolant bleed",
  s21: "s21 · LPT coolant bleed",
};

export default function EnginePage() {
  const id = Number(useParams().id);
  const { data, isError, error } = useEngine(id);
  const [sensor, setSensor] = useState("s11");
  const ack = useAcknowledge();
  const { isEngineer } = useRoles();

  const latest = data?.predictions[data.predictions.length - 1];
  const sensors = useMemo(
    () => (data?.readings[0] ? Object.keys(data.readings[0]).filter((k) => k !== "cycle") : []),
    [data],
  );

  if (isError) return <p className="error">{String(error)}</p>;
  if (!data || !latest) return <p className="muted">Loading engine {id}…</p>;

  return (
    <>
      <Link to="/fleet" className="back">
        ← Fleet
      </Link>
      <div className="page-head">
        <div>
          <h1>Engine {id}</h1>
          <p className="muted">
            Cycle {latest.cycle} · predicted RUL {latest.rul_pred.toFixed(0)} cycles
          </p>
        </div>
        <BandBadge band={latest.band} />
      </div>

      <section className="panel">
        <h2>Predicted remaining useful life</h2>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data.predictions} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="cycle" stroke="var(--muted)" fontSize={12} />
            <YAxis stroke="var(--muted)" fontSize={12} domain={[0, 130]} />
            <Tooltip
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }}
              formatter={(v: number) => [`${v.toFixed(1)} cycles`, "Predicted RUL"]}
              labelFormatter={(c) => `Cycle ${c}`}
            />
            <ReferenceLine y={50} stroke="var(--warning)" strokeDasharray="4 4" label={{ value: "warning", fill: "var(--warning)", fontSize: 11, position: "insideTopRight" }} />
            <ReferenceLine y={20} stroke="var(--critical)" strokeDasharray="4 4" label={{ value: "critical", fill: "var(--critical)", fontSize: 11, position: "insideTopRight" }} />
            <Line type="monotone" dataKey="rul_pred" stroke="var(--accent)" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Sensor</h2>
          <select value={sensor} onChange={(e) => setSensor(e.target.value)} aria-label="Sensor">
            {sensors.map((s) => (
              <option key={s} value={s}>
                {SENSOR_LABELS[s] ?? s}
              </option>
            ))}
          </select>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data.readings} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="cycle" stroke="var(--muted)" fontSize={12} />
            <YAxis stroke="var(--muted)" fontSize={12} domain={["auto", "auto"]} width={64} />
            <Tooltip
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }}
              labelFormatter={(c) => `Cycle ${c}`}
            />
            <Line type="monotone" dataKey={sensor} stroke="var(--series2)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </section>

      <section className="panel">
        <h2>Alerts</h2>
        <AlertsTable
          alerts={data.alerts}
          canAcknowledge={isEngineer}
          onAcknowledge={(alertId) => ack.mutate(alertId)}
          pendingId={ack.isPending ? ack.variables : null}
        />
      </section>
    </>
  );
}
