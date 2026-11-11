import React, { useState } from 'react';
import {
  Wallet,
  ArrowDownLeft,
  ArrowUpRight,
  RefreshCcw,
  Plus,
  ShieldCheck,
  Search,
  X,
  FileSpreadsheet,
} from 'lucide-react';
import { UserWallet, WalletTransaction } from '../types/store';
import { formatMYR, calculateWalletTransaction } from '../utils/store-logic';

interface WalletManagementProps {
  totalBalance: number;
  wallets: UserWallet[];
  transactions: WalletTransaction[];
  onAdjustBalance: (userId: number, amount: number, kind: WalletTransaction['kind'], note: string) => Promise<void>;
}

export const WalletManagement: React.FC<WalletManagementProps> = ({
  totalBalance,
  wallets,
  transactions,
  onAdjustBalance,
}) => {
  const [search, setSearch] = useState('');
  const [isAdjustModalOpen, setIsAdjustModalOpen] = useState(false);
  const [targetUserId, setTargetUserId] = useState<number>(wallets[0]?.user_id || 0);
  const [adjustAmount, setAdjustAmount] = useState<number>(10);
  const [adjustKind, setAdjustKind] = useState<WalletTransaction['kind']>('topup');
  const [adjustNote, setAdjustNote] = useState('');
  const [loading, setLoading] = useState(false);

  const filteredWallets = wallets.filter(w => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return w.username.toLowerCase().includes(q) || String(w.user_id).includes(q);
  });

  const handleAdjustSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetUserId || !adjustAmount) return;

    setLoading(true);
    try {
      const realAmount = adjustKind === 'debit' ? -Math.abs(adjustAmount) : Math.abs(adjustAmount);
      await onAdjustBalance(targetUserId, realAmount, adjustKind, adjustNote);
      setIsAdjustModalOpen(false);
      setAdjustNote('');
    } catch (err: any) {
      console.error('Wallet adjust failed:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold text-white font-display">Dompet AI Pelanggan & Lejar Atomik</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Pengurusan baki kredit Berry AI Studio pelanggan, rekod caj idempotensi & pelarasan manual
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            setTargetUserId(wallets[0]?.user_id || 0);
            setIsAdjustModalOpen(true);
          }}
          className="px-3.5 py-2 bg-pink-600 hover:bg-pink-500 text-white text-xs font-semibold rounded-xl flex items-center gap-1.5 transition-colors cursor-pointer self-start sm:self-auto shadow-md shadow-pink-600/20"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Laras Baki Dompet</span>
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-xs text-slate-400">Total AI Wallet Liabilities (MYR)</div>
          <div className="text-2xl font-bold text-purple-400 font-mono mt-1 tabular-nums">
            {formatMYR(totalBalance)}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">Jumlah kredit pelanggan sedia digunakan</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-xs text-slate-400">Akaun Dompet Aktif</div>
          <div className="text-2xl font-bold text-white font-mono mt-1 tabular-nums">{wallets.length} pengguna</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Mempunyai baki positif atau rekod transaksi</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-xs text-slate-400">Integriti Transaksi Lejar</div>
          <div className="text-sm font-semibold text-emerald-400 mt-2 flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4" />
            <span>Kekunci Idempotensi & Anti-Overdraft</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">Menjamin tiada pertindihan caj berlaku</div>
        </div>
      </div>

      {/* Wallets & Transactions Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* User Wallets Directory */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
          <div className="p-4 border-b border-slate-800 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">Baki Pengguna</h3>
            <span className="text-xs text-slate-400 font-mono">{wallets.length} rekod</span>
          </div>

          <div className="divide-y divide-slate-800/60 max-h-96 overflow-y-auto">
            {filteredWallets.map(w => (
              <div key={w.user_id} className="p-3.5 hover:bg-slate-800/40 transition-colors flex items-center justify-between">
                <div>
                  <div className="font-semibold text-white text-xs">@{w.username}</div>
                  <div className="text-[10px] text-slate-400 font-mono">ID: {w.user_id}</div>
                </div>
                <div className="text-right">
                  <div className="font-mono font-bold text-purple-400 text-xs tabular-nums">
                    {formatMYR(w.balance)}
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setTargetUserId(w.user_id);
                      setIsAdjustModalOpen(true);
                    }}
                    className="text-[10px] text-pink-400 hover:underline cursor-pointer"
                  >
                    Laras
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Transactions Ledger */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
          <div className="p-4 border-b border-slate-800 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white">Lejar Transaksi Terkini</h3>
              <p className="text-xs text-slate-400">Jejak audit setiap tambah nilai, caj penjanaan AI & bayaran balik</p>
            </div>
            <span className="text-xs font-mono text-pink-400 bg-pink-500/10 px-2.5 py-1 rounded-md border border-pink-500/20">
              Real-time Ledger
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/60 text-slate-400 uppercase font-mono tracking-wider border-b border-slate-800">
                <tr>
                  <th className="px-4 py-3">ID & Pengguna</th>
                  <th className="px-4 py-3">Jenis</th>
                  <th className="px-4 py-3 text-right">Amaun (RM)</th>
                  <th className="px-4 py-3 text-right">Baki Selepas</th>
                  <th className="px-4 py-3">Nota & Idempotensi</th>
                  <th className="px-4 py-3">Masa</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-200">
                {transactions.map(tx => (
                  <tr key={tx.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-semibold text-white">@{tx.username || tx.user_id}</div>
                      <div className="text-[10px] text-slate-400 font-mono">#{tx.id}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${
                          tx.kind === 'topup'
                            ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                            : tx.kind === 'debit'
                            ? 'bg-pink-500/15 text-pink-300 border border-pink-500/30'
                            : 'bg-purple-500/15 text-purple-300 border border-purple-500/30'
                        }`}
                      >
                        {tx.kind.toUpperCase()}
                      </span>
                    </td>
                    <td
                      className={`px-4 py-3 text-right font-mono font-bold tabular-nums ${
                        tx.amount >= 0 ? 'text-emerald-400' : 'text-pink-400'
                      }`}
                    >
                      {tx.amount >= 0 ? `+${formatMYR(tx.amount)}` : formatMYR(tx.amount)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-semibold text-slate-300 tabular-nums">
                      {formatMYR(tx.balance_after)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-slate-300 text-xs">{tx.note || 'Transaksi lejar'}</div>
                      <div className="text-[9px] text-slate-400 font-mono truncate max-w-xs">
                        {tx.idempotency_key}
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-[11px] text-slate-400">
                      {new Date(tx.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ADJUST WALLET MODAL */}
      {isAdjustModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
              <h3 className="text-base font-bold text-white font-display">
                Laras Baki Dompet Pelanggan
              </h3>
              <button
                type="button"
                onClick={() => setIsAdjustModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleAdjustSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Pilih Pengguna Sasaran</label>
                <select
                  value={targetUserId}
                  onChange={e => setTargetUserId(Number(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-pink-500 font-mono"
                >
                  {wallets.map(w => (
                    <option key={w.user_id} value={w.user_id}>
                      @{w.username} (Baki semasa: {formatMYR(w.balance)})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Tindakan</label>
                  <select
                    value={adjustKind}
                    onChange={e => setAdjustKind(e.target.value as any)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-pink-500"
                  >
                    <option value="topup">Top-up (+ Kredit)</option>
                    <option value="debit">Tolak / Debit (- Kredit)</option>
                    <option value="refund">Bayaran Balik (Refund)</option>
                    <option value="adjustment">Pelarasan Pembetulan</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Jumlah (MYR)</label>
                  <input
                    type="number"
                    step="0.50"
                    min="0.50"
                    required
                    value={adjustAmount}
                    onChange={e => setAdjustAmount(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 font-mono focus:outline-none focus:border-pink-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Sebab / Rujukan Audit</label>
                <input
                  type="text"
                  required
                  value={adjustNote}
                  onChange={e => setAdjustNote(e.target.value)}
                  placeholder="Contoh: Pengesahan bayaran manual DuitNow / Ganti rugi AI timeout"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-pink-500"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsAdjustModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl cursor-pointer"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="px-4 py-2 bg-pink-600 hover:bg-pink-500 text-white rounded-xl font-semibold cursor-pointer shadow-md disabled:opacity-50"
                >
                  {loading ? 'Memproses Lejar...' : 'Laksanakan Pelarasan'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
