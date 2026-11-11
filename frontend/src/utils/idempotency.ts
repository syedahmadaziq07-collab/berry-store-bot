/** Keep the same key after an ambiguous network/5xx result; never auto-retry writes. */
export class MutationKeys {
  private pending = new Map<string, string>();
  acquire(fingerprint: string, createKey: () => string): string {
    const existing = this.pending.get(fingerprint);
    if (existing) return existing;
    if (this.pending.size >= 100) throw new Error('Terlalu banyak transaksi belum disahkan. Semak audit sebelum tindakan baharu.');
    const key = createKey();
    this.pending.set(fingerprint, key);
    return key;
  }
  settle(fingerprint: string, status: number): void {
    if ((status >= 200 && status < 300) || [400,401,403,404,405,413,422,423,429].includes(status)) {
      this.pending.delete(fingerprint);
    }
  }
}
