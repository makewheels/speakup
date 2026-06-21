// Python/MongoDB often omits the Z suffix on UTC strings; appending it ensures
// the browser treats the value as UTC and then converts to browser-local time.
export function formatDateTime(iso) {
  if (!iso) return "";
  const s = /Z|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + "Z";
  const d = new Date(s);
  if (isNaN(d)) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
