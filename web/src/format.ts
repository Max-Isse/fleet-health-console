export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatCount(n: number | undefined): string {
  return n === undefined ? "–" : n.toLocaleString();
}
