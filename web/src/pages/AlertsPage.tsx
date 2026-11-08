import { useState } from "react";
import { useAcknowledge, useAlerts } from "../api";
import { useRoles } from "../auth";
import AlertsTable from "../components/AlertsTable";

type Status = "open" | "acknowledged" | "all";

export default function AlertsPage() {
  const [status, setStatus] = useState<Status>("open");
  const { data, isError, error } = useAlerts(status);
  const ack = useAcknowledge();
  const { isEngineer } = useRoles();

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Alerts</h1>
          <p className="muted">
            Raised once per engine when it first enters the warning or critical band.
            {!isEngineer && " You can view alerts; acknowledging needs the engineer role."}
          </p>
        </div>
      </div>
      <div className="filters" role="group" aria-label="Alert status">
        {(["open", "acknowledged", "all"] as Status[]).map((s) => (
          <button key={s} className={`chip ${status === s ? "active" : ""}`} onClick={() => setStatus(s)}>
            {s[0].toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>
      {ack.isError && <p className="error">Could not acknowledge: {String(ack.error)}</p>}
      {isError && <p className="error">{String(error)}</p>}
      {data && (
        <AlertsTable
          alerts={data}
          canAcknowledge={isEngineer}
          onAcknowledge={(id) => ack.mutate(id)}
          pendingId={ack.isPending ? ack.variables : null}
        />
      )}
    </>
  );
}
