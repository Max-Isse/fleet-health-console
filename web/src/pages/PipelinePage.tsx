import { usePipeline } from "../api";
import Stat from "../components/Stat";
import { formatCount, formatTime } from "../format";

export default function PipelinePage() {
  const { data, isError, error } = usePipeline();
  if (isError) return <p className="error">{String(error)}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  const kafka = "error" in data.kafka ? null : data.kafka;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Pipeline</h1>
          <p className="muted">
            Consumer group health for <code>{kafka?.topic ?? "engine-telemetry"}</code>. Offsets are committed only
            after the database transaction commits, so lag counts messages not yet safely stored.
          </p>
        </div>
      </div>

      <section className="stats">
        <Stat label="Consumer lag (messages)" value={kafka ? formatCount(kafka.total_lag) : "–"} tone={kafka && kafka.total_lag > 1000 ? "warning" : undefined} />
        <Stat label="Readings stored" value={formatCount(data.database.readings)} />
        <Stat label="Predictions" value={formatCount(data.database.predictions)} />
        <Stat label="Dead letters" value={formatCount(data.database.dead_letters)} tone={data.database.dead_letters ? "warning" : undefined} />
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Partitions</h2>
          {kafka && (
            <span className="muted">
              group <code>{kafka.group}</code> · {kafka.state.toLowerCase()} · last new reading{" "}
              {formatTime(data.database.last_ingested_at)}
            </span>
          )}
        </div>
        {!kafka && <p className="error">Kafka status unavailable.</p>}
        {kafka && (
          <table className="table">
            <thead>
              <tr>
                <th className="num">Partition</th>
                <th className="num">Committed offset</th>
                <th className="num">End offset</th>
                <th className="num">Lag</th>
                <th>Owner</th>
              </tr>
            </thead>
            <tbody>
              {kafka.partitions.map((p) => (
                <tr key={p.partition}>
                  <td className="num">{p.partition}</td>
                  <td className="num">{formatCount(p.committed_offset)}</td>
                  <td className="num">{formatCount(p.end_offset)}</td>
                  <td className="num">{formatCount(p.lag)}</td>
                  <td className="muted">{p.owner ?? "unassigned"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel">
        <h2>Recent dead letters</h2>
        <p className="muted">
          Messages that broke the event contract. They are stored and sent to <code>engine-telemetry.dlq</code> so the
          partition keeps moving.
        </p>
        {data.dead_letters.length === 0 ? (
          <p className="empty">None.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Error</th>
                <th>Payload</th>
                <th>Received</th>
              </tr>
            </thead>
            <tbody>
              {data.dead_letters.map((d) => (
                <tr key={d.id}>
                  <td className="num">
                    {d.kafka_partition}:{d.kafka_offset}
                  </td>
                  <td>{d.error}</td>
                  <td>
                    <code className="payload">{d.payload}</code>
                  </td>
                  <td className="muted">{formatTime(d.received_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
