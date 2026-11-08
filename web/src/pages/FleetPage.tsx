import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useEngines, usePipeline } from "../api";
import BandBadge from "../components/BandBadge";
import Stat from "../components/Stat";
import { formatCount, formatTime } from "../format";
import type { Band } from "../types";

const RUL_CAP = 125;
const FILTERS: (Band | undefined)[] = [undefined, "critical", "warning", "healthy"];

export default function FleetPage() {
  const [band, setBand] = useState<Band | undefined>(undefined);
  const all = useEngines();
  const shown = useEngines(band);
  const pipeline = usePipeline();
  const navigate = useNavigate();

  const engines = all.data ?? [];
  const count = (b: Band) => engines.filter((e) => e.band === b).length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Fleet</h1>
          <p className="muted">Latest predicted remaining useful life (RUL) per engine, most at risk first.</p>
        </div>
        <span className="live">
          <span className="dot" /> Live
        </span>
      </div>

      <section className="stats">
        <Stat label="Engines reporting" value={formatCount(engines.length)} />
        <Stat label="Critical (< 20 cycles)" value={formatCount(count("critical"))} tone="critical" />
        <Stat label="Warning (< 50 cycles)" value={formatCount(count("warning"))} tone="warning" />
        <Stat label="Open alerts" value={formatCount(pipeline.data?.database.open_alerts)} />
      </section>

      <div className="filters" role="group" aria-label="Filter by band">
        {FILTERS.map((f) => (
          <button key={f ?? "all"} className={`chip ${band === f ? "active" : ""}`} onClick={() => setBand(f)}>
            {f ? f[0].toUpperCase() + f.slice(1) : "All"}
          </button>
        ))}
      </div>

      {shown.isError && <p className="error">Could not load engines: {String(shown.error)}</p>}
      {shown.data && shown.data.length === 0 && (
        <p className="empty">No engines yet. Start the replay: docker compose run --rm producer</p>
      )}
      {shown.data && shown.data.length > 0 && (
        <table className="table clickable">
          <thead>
            <tr>
              <th>Engine</th>
              <th className="num">Cycle</th>
              <th>Predicted RUL</th>
              <th>Band</th>
              <th>Scored</th>
            </tr>
          </thead>
          <tbody>
            {shown.data.map((e) => (
              <tr key={e.engine_id} onClick={() => navigate(`/engines/${e.engine_id}`)}>
                <td>Engine {e.engine_id}</td>
                <td className="num">{e.cycle}</td>
                <td>
                  <div className="rul">
                    <div className="rul-track">
                      <div
                        className={`rul-fill rul-${e.band}`}
                        style={{ width: `${Math.min(100, (e.rul_pred / RUL_CAP) * 100)}%` }}
                      />
                    </div>
                    <span className="num">{e.rul_pred.toFixed(0)}</span>
                  </div>
                </td>
                <td>
                  <BandBadge band={e.band} />
                </td>
                <td className="muted">{formatTime(e.scored_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
