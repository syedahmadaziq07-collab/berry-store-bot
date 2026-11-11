/** Treat user-controlled text as literal cells, including spreadsheet formulas. */
export function csvCell(value: string | number | null | undefined): string {
  let text = String(value ?? '');
  if (typeof value === 'string' && /^[\s\u0000-\u001f]*[=+@-]/u.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
export function ordersCsv(rows: Array<{id: string; user_id: number; username: string; product_name: string; amount: number; status: string; created_at: string; notes?: string}>): string {
  return '\uFEFF' + [['Order ID', 'Telegram User ID', 'Username', 'Product', 'Amount RM', 'Status', 'Date', 'Notes'],
    ...rows.map(o => [o.id, o.user_id, o.username, o.product_name, o.amount.toFixed(2), o.status, o.created_at, o.notes || ''])]
    .map(row => row.map(csvCell).join(',')).join('\r\n');
}
