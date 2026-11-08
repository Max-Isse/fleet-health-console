export default function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className={`stat ${tone ? `stat-${tone}` : ""}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
