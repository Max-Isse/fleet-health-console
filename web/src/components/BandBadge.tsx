import type { Band } from "../types";

const LABEL: Record<Band, string> = { healthy: "Healthy", warning: "Warning", critical: "Critical" };

export default function BandBadge({ band }: { band: Band }) {
  return <span className={`badge badge-${band}`}>{LABEL[band]}</span>;
}
