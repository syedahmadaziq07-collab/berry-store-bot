import React, { useState } from 'react';
import {
  Gift,
  Award,
  Plus,
  Ticket,
  Save,
  Trash2,
  CheckCircle2,
  X,
} from 'lucide-react';
import { Customer } from '../types/store';
import { formatMYR } from '../utils/store-logic';

interface ReferralSystemProps {
  customers: Customer[];
  referralRewardRM: string;
  onUpdateReward: (rewardRM: string) => Promise<void>;
}

export const ReferralSystem: React.FC<ReferralSystemProps> = ({
  customers,
  referralRewardRM,
  onUpdateReward,
}) => {
  const [rewardInput, setRewardInput] = useState(referralRewardRM);
  const [isSavingReward, setIsSavingReward] = useState(false);
  const [rewardSaved, setRewardSaved] = useState(false);

  // Vouchers state
  const vouchers: any[] = []; // No voucher schema exists; never seed prototype codes.

  const [isVoucherModalOpen, setIsVoucherModalOpen] = useState(false);
  const [newCode, setNewCode] = useState('');
  const [newDiscount, setNewDiscount] = useState<number>(10);
  const [newMaxUses, setNewMaxUses] = useState<number>(100);

  // Top referrers
  const leaderboard = [...customers]
    .filter(c => c.referral_count > 0)
    .sort((a, b) => b.referral_count - a.referral_count);

  const handleSaveReward = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSavingReward(true);
    setRewardSaved(false);
    try {
      await onUpdateReward(rewardInput);
      setRewardSaved(true);
      setTimeout(() => setRewardSaved(false), 3000);
    } finally {
      setIsSavingReward(false);
    }
  };

  const handleCreateVoucher = (e: React.FormEvent) => {
    e.preventDefault();
    window.dispatchEvent(new CustomEvent('api-error', {detail: 'Baucar belum tersedia dalam backend sebenar.'}));
  };

  const handleDeleteVoucher = (id: string) => { window.dispatchEvent(new CustomEvent('api-error', {detail: 'Baucar belum tersedia'})); };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold text-white font-display">Program Rujukan (Referral) & Baucar Diskaun</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Kredit automatik ke dompet bagi setiap pengguna yang mengajak rakan & pengurusan kod promosi
          </p>
        </div>

        <button
          type="button"
          onClick={() => window.dispatchEvent(new CustomEvent('api-error', {detail: 'Modul baucar memerlukan schema dan API sebenar.'}))}
          className="px-3.5 py-2 bg-pink-600 hover:bg-pink-500 text-white text-xs font-semibold rounded-xl flex items-center gap-1.5 transition-colors cursor-pointer self-start sm:self-auto shadow-md shadow-pink-600/20"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Cipta Kod Baucar</span>
        </button>
      </div>

      {/* Reward Setting & Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Reward Setting Form */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 text-pink-400 text-xs font-semibold mb-2">
              <Gift className="w-4 h-4" />
              <span>Ganjaran Kredit Setiap Rujukan</span>
            </div>
            <p className="text-xs text-slate-300 mb-4">
              Amaun yang akan dikreditkan secara automatik ke akaun dompet perujuk apabila rakan selesai membuat belian pertama.
            </p>

            <form onSubmit={handleSaveReward} className="space-y-3">
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Ganjaran Rujukan (MYR):</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 font-mono text-xs">RM</span>
                  <input
                    type="number"
                    step="0.50"
                    min="0"
                    value={rewardInput}
                    onChange={e => setRewardInput(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-3 py-2 text-white font-mono text-xs focus:outline-none focus:border-pink-500"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isSavingReward}
                className="w-full py-2 bg-pink-600 hover:bg-pink-500 text-white font-semibold text-xs rounded-xl transition-all cursor-pointer shadow-md disabled:opacity-50"
              >
                {isSavingReward ? 'Menyimpan...' : 'Kemaskini Ganjaran'}
              </button>
            </form>
          </div>

          {rewardSaved && (
            <div className="mt-2 text-[11px] text-emerald-400 flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Ganjaran rujukan dikemaskini!</span>
            </div>
          )}
        </div>

        {/* Total Referral Metrics */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <div>
            <div className="text-xs text-slate-400">Jumlah Jemputan Direkodkan</div>
            <div className="text-2xl font-bold text-white font-mono mt-1 tabular-nums">
              {customers.reduce((sum, c) => sum + c.referral_count, 0)} orang
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Pelanggan baharu yang masuk ke bot Telegram melalui pautan jemputan khas kawan.
            </p>
          </div>
          <div className="pt-3 border-t border-slate-800 text-xs text-emerald-400 font-medium">
            Kos iklan dan penjimatan belum diukur
          </div>
        </div>

        {/* Protection Safeguard */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <div>
            <div className="text-xs text-slate-400">Kawalan Anti-Penipuan (Anti-Abuse)</div>
            <div className="text-sm font-semibold text-pink-400 mt-1 flex items-center gap-1.5">
              <span>Satu Rujukan = Min. 1 Pesanan Selesai</span>
            </div>
            <p className="text-xs text-slate-300 mt-2">
              Semakan anti-abuse dan ganjaran memerlukan ujian transaksi sebelum diaktifkan.
            </p>
          </div>
          <div className="pt-3 border-t border-slate-800 text-xs text-slate-400">
            Status: <span className="text-emerald-400 font-mono">Belum disahkan</span>
          </div>
        </div>
      </div>

      {/* Leaderboard & Vouchers Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Referral Leaderboard */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
          <div className="p-4 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Award className="w-4 h-4 text-amber-400" />
              <h3 className="text-sm font-semibold text-white">Carta Pemimpin Rujukan (Leaderboard)</h3>
            </div>
            <span className="text-xs text-slate-400 font-mono">Top Duta</span>
          </div>

          <div className="divide-y divide-slate-800/60 max-h-80 overflow-y-auto">
            {leaderboard.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-400">
                Belum ada rujukan dicatatkan.
              </div>
            ) : (
              leaderboard.map((c, idx) => (
                <div key={c.id} className="p-3.5 hover:bg-slate-800/40 transition-colors flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className={`w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs font-mono ${
                      idx === 0 ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40' :
                      idx === 1 ? 'bg-slate-400/20 text-slate-300 border border-slate-400/40' :
                      idx === 2 ? 'bg-amber-700/20 text-amber-600 border border-amber-700/40' :
                      'bg-slate-800 text-slate-400'
                    }`}>
                      {idx + 1}
                    </span>
                    <div>
                      <div className="font-semibold text-white text-xs">{c.name} (@{c.username})</div>
                      <div className="text-[10px] text-slate-400 font-mono">ID: {c.id}</div>
                    </div>
                  </div>

                  <div className="text-right">
                    <div className="font-mono font-bold text-pink-400 text-xs">
                      {c.referral_count} jemputan
                    </div>
                    <div className="text-[10px] text-emerald-400 font-mono">
                      Bayaran ganjaran belum disahkan
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Voucher Codes Manager */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
          <div className="p-4 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Ticket className="w-4 h-4 text-pink-400" />
              <h3 className="text-sm font-semibold text-white">Kod Baucar Diskaun Telegram</h3>
            </div>
            <span className="text-xs text-slate-400 font-mono">{vouchers.length} kod aktif</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/60 text-slate-400 uppercase font-mono tracking-wider border-b border-slate-800">
                <tr>
                  <th className="px-4 py-3">Kod</th>
                  <th className="px-4 py-3 text-center">Diskaun</th>
                  <th className="px-4 py-3 text-center">Penggunaan</th>
                  <th className="px-4 py-3">Tamat</th>
                  <th className="px-4 py-3 text-right">Padam</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-200"><tr><td colSpan={5} className="p-4 text-slate-400">Baucar belum tersedia dalam database.</td></tr>
                {vouchers.map(v => (
                  <tr key={v.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3 font-mono font-bold text-pink-400">
                      {v.code}
                    </td>
                    <td className="px-4 py-3 text-center font-mono font-semibold text-emerald-400">
                      {v.discount_pct}% OFF
                    </td>
                    <td className="px-4 py-3 text-center font-mono text-slate-300">
                      {v.used_count} / {v.max_uses}
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-400 text-[11px]">
                      {v.expiry}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => handleDeleteVoucher(v.id)}
                        className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors cursor-pointer"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* CREATE VOUCHER MODAL */}
      {isVoucherModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
              <h3 className="text-base font-bold text-white font-display">
                Cipta Kod Baucar Diskaun Baharu
              </h3>
              <button
                type="button"
                onClick={() => setIsVoucherModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateVoucher} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Kod Baucar</label>
                <input
                  type="text"
                  required
                  value={newCode}
                  onChange={e => setNewCode(e.target.value)}
                  placeholder="Contoh: MERDEKA50, PROMOBERRY"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white font-mono uppercase focus:outline-none focus:border-pink-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Diskaun (%)</label>
                  <input
                    type="number"
                    min="1"
                    max="100"
                    required
                    value={newDiscount}
                    onChange={e => setNewDiscount(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white font-mono focus:outline-none focus:border-pink-500"
                  />
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Had Tebus Maksimum</label>
                  <input
                    type="number"
                    min="1"
                    required
                    value={newMaxUses}
                    onChange={e => setNewMaxUses(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white font-mono focus:outline-none focus:border-pink-500"
                  />
                </div>
              </div>

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsVoucherModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl cursor-pointer"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-pink-600 hover:bg-pink-500 text-white rounded-xl font-semibold cursor-pointer shadow-md"
                >
                  Aktifkan Baucar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
