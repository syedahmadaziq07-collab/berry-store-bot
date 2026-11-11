import React, { useState } from 'react';
import {
  Search,
  User,
  ShieldCheck,
  ShieldAlert,
  Edit,
  Save,
  Wallet,
  ShoppingBag,
  Gift,
  X,
} from 'lucide-react';
import { Customer } from '../types/store';
import { formatMYR } from '../utils/store-logic';

interface CustomerDirectoryProps {
  customers: Customer[];
  onUpdateCustomer: (id: number, notes: string, status: Customer['status']) => Promise<void>;
}

export const CustomerDirectory: React.FC<CustomerDirectoryProps> = ({
  customers,
  onUpdateCustomer,
}) => {
  const [search, setSearch] = useState('');
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [notesDraft, setNotesDraft] = useState('');
  const [statusDraft, setStatusDraft] = useState<Customer['status']>('active');

  const filtered = customers.filter(c => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return c.username.toLowerCase().includes(q) || c.name.toLowerCase().includes(q) || String(c.id).includes(q);
  });

  const handleOpenDrawer = (c: Customer) => {
    setSelectedCustomer(c);
    setNotesDraft(c.notes || '');
    setStatusDraft(c.status);
  };

  const handleSaveCustomerNotes = async () => {
    if (!selectedCustomer) return;
    await onUpdateCustomer(selectedCustomer.id, notesDraft, statusDraft);
    setSelectedCustomer({
      ...selectedCustomer,
      notes: notesDraft,
      status: statusDraft,
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold text-white font-display">Direktori Pelanggan Telegram</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Lihat rekod pesanan, baki dompet AI & nota sulit admin untuk setiap pengguna Telegram bot
          </p>
        </div>

        {/* Search */}
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Cari ID Telegram, username..."
            className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-pink-500"
          />
        </div>
      </div>

      {/* Customer Directory Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 text-slate-400 uppercase font-mono tracking-wider border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">Pelanggan Telegram</th>
                <th className="px-4 py-3">Tarikh Sertai</th>
                <th className="px-4 py-3 text-center">Pesanan</th>
                <th className="px-4 py-3 text-right">Jumlah Belanja</th>
                <th className="px-4 py-3 text-right">Baki Dompet</th>
                <th className="px-4 py-3 text-center">Rujukan</th>
                <th className="px-4 py-3 text-center">Status</th>
                <th className="px-4 py-3 text-right">Profil</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-200">
              {filtered.map(c => (
                <tr key={c.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-pink-600 to-purple-600 text-white font-bold flex items-center justify-center text-xs shrink-0">
                        {c.name.slice(0, 1)}
                      </div>
                      <div>
                        <div className="font-semibold text-white">{c.name}</div>
                        <div className="text-[11px] text-pink-400">@{c.username}</div>
                        <div className="text-[10px] text-slate-400 font-mono">ID: {c.id}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-slate-400">
                    {new Date(c.joined_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-center font-mono font-semibold text-white">
                    {c.total_orders}
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-bold text-white tabular-nums">
                    {formatMYR(c.total_spent)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-semibold text-purple-400 tabular-nums">
                    {formatMYR(c.wallet_balance)}
                  </td>
                  <td className="px-4 py-3 text-center font-mono text-slate-300">
                    {c.referral_count}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span
                      className={`inline-block px-2.5 py-0.5 rounded-md text-[11px] font-mono ${
                        c.status === 'active'
                          ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                          : 'bg-red-500/15 text-red-300 border border-red-500/30'
                      }`}
                    >
                      {c.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => handleOpenDrawer(c)}
                      className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors cursor-pointer"
                    >
                      Butiran
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* CUSTOMER DETAIL MODAL / DRAWER */}
      {selectedCustomer && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg p-6 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-pink-600 flex items-center justify-center text-white font-bold text-base">
                  {selectedCustomer.name.slice(0, 1)}
                </div>
                <div>
                  <h3 className="text-base font-bold text-white font-display">
                    {selectedCustomer.name}
                  </h3>
                  <div className="text-xs text-pink-400 font-mono">
                    @{selectedCustomer.username} · ID: {selectedCustomer.id}
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedCustomer(null)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              {/* Quick Stat Cards */}
              <div className="grid grid-cols-3 gap-2">
                <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800 text-center">
                  <div className="text-slate-400 text-[10px]">Jumlah Pesanan</div>
                  <div className="font-mono font-bold text-white text-sm mt-0.5">{selectedCustomer.total_orders}</div>
                </div>
                <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800 text-center">
                  <div className="text-slate-400 text-[10px]">Jumlah Belanja</div>
                  <div className="font-mono font-bold text-emerald-400 text-sm mt-0.5">{formatMYR(selectedCustomer.total_spent)}</div>
                </div>
                <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800 text-center">
                  <div className="text-slate-400 text-[10px]">Baki Dompet AI</div>
                  <div className="font-mono font-bold text-purple-400 text-sm mt-0.5">{formatMYR(selectedCustomer.wallet_balance)}</div>
                </div>
              </div>

              {/* Status Selector */}
              <div>
                <label className="block text-slate-300 font-medium mb-1">Status Akaun</label>
                <select
                  value={statusDraft}
                  onChange={e => setStatusDraft(e.target.value as any)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-pink-500"
                >
                  <option value="active">Active (Biasa)</option>
                  <option value="restricted">Restricted (Dihadkan)</option>
                  <option value="blocked">Blocked (Disekat dari Telegram Bot)</option>
                </select>
              </div>

              {/* Admin Notes */}
              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Nota Sulit Admin (Hanya kelihatan kepada pemilik kedai):
                </label>
                <textarea
                  rows={4}
                  value={notesDraft}
                  onChange={e => setNotesDraft(e.target.value)}
                  placeholder="Contoh: Pelanggan setia, suka pakej Netflix 3 bulan, pernah minta ganti profil..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-slate-100 focus:outline-none focus:border-pink-500"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setSelectedCustomer(null)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl cursor-pointer"
                >
                  Tutup
                </button>
                <button
                  type="button"
                  onClick={handleSaveCustomerNotes}
                  className="px-4 py-2 bg-pink-600 hover:bg-pink-500 text-white rounded-xl font-semibold cursor-pointer shadow-md flex items-center gap-1.5"
                >
                  <Save className="w-3.5 h-3.5" />
                  <span>Simpan Perubahan</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
