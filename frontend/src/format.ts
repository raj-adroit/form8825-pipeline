export function formatCurrency(value: number): string {
  const sign = value < 0 ? "-" : ""
  return `${sign}$${Math.abs(value).toLocaleString("en-US")}`
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString()
}
