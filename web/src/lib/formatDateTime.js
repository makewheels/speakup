// Always display in Asia/Shanghai (UTC+8) regardless of browser timezone.
// sv-SE locale produces YYYY-MM-DD HH:MM:SS — slice to drop milliseconds.
export function formatDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return d.toLocaleString("sv-SE", { timeZone: "Asia/Shanghai" }).slice(0, 19);
}
