import { Link } from "react-router-dom";
import type { Alert } from "../types";
import BandBadge from "./BandBadge";
import { formatTime } from "../format";

interface Props {
  alerts: Alert[];
  canAcknowledge: boolean;
  onAcknowledge: (id: number) => void;
  pendingId?: number | null;
}

export default function AlertsTable({ alerts, canAcknowledge, onAcknowledge, pendingId }: Props) {
  if (alerts.length === 0) return <p className="empty">No alerts here.</p>;
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Engine</th>
          <th>Band</th>
          <th className="num">Cycle</th>
          <th className="num">Predicted RUL</th>
          <th>Raised</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {alerts.map((a) => (
          <tr key={a.id}>
            <td>
              <Link to={`/engines/${a.engine_id}`}>Engine {a.engine_id}</Link>
            </td>
            <td>
              <BandBadge band={a.band} />
            </td>
            <td className="num">{a.cycle}</td>
            <td className="num">{a.rul_pred.toFixed(0)} cycles</td>
            <td>{formatTime(a.raised_at)}</td>
            <td>
              {a.acknowledged_at ? (
                <span className="muted">
                  Acknowledged by {a.acknowledged_by} · {formatTime(a.acknowledged_at)}
                </span>
              ) : (
                <button
                  className="small"
                  disabled={!canAcknowledge || pendingId === a.id}
                  title={canAcknowledge ? "Mark as seen and being handled" : "Needs the engineer role"}
                  onClick={() => onAcknowledge(a.id)}
                >
                  {pendingId === a.id ? "Saving…" : "Acknowledge"}
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
