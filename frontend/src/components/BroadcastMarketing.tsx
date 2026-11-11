import React, { useState } from 'react';
import {
  Send,
  Users,
  Image,
  Clock,
  CheckCircle2,
  AlertCircle,
  Sparkles,
} from 'lucide-react';

interface BroadcastMarketingProps {
  broadcasts: any[];
  customerCount: number;
  onSendBroadcast: (title: string, message: string, audience: string) => Promise<void>;
}

export const BroadcastMarketing: React.FC<BroadcastMarketingProps> = ({
  broadcasts,
  customerCount,
  onSendBroadcast,
}) => {
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [audience, setAudience] = useState('All Active Users');
  const [isSending, setIsSending] = useState(false);
  const [successMsg, setSuccessMsg] = useState(false);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim()) return;

    setIsSending(true);
    setSuccessMsg(false);
    try {
      await onSendBroadcast(title || 'Pengumuman Penting', message, audience);
      setTitle('');
      setMessage('');
      setSuccessMsg(true);
      setTimeout(() => setSuccessMsg(false), 4000);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-xl font-bold text-white font-display">Siaran Pemasaran Telegram (Broadcast)</h1>
        <p className="text-xs text-slate-400 mt-0.5">
          Hantar mesej promosi, tawaran diskaun & kemas kini terus ke peti mesej semua pelanggan Telegram bot
        </p>
      </div>

      {successMsg && (
        <div className="p-3 bg-emerald-950/60 border border-emerald-800/80 rounded-xl text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>Kempen siaran berjaya dihantar ke barisan giliran Telegram bot!</span>
        </div>
      )}

      {/* Composer & Preview Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Composer Form */}
        <form onSubmit={handleSend} className="lg:col-span-3 bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4 shadow-lg text-xs">
          <h3 className="text-sm font-semibold text-white border-b border-slate-800 pb-2 flex items-center gap-2">
            <Send className="w-4 h-4 text-pink-400" />
            <span>Tulis Mesej Siaran Baharu</span>
          </h3>

          <div>
            <label className="block text-slate-300 font-medium mb-1">Tajuk / Rujukan Kempen</label>
            <input
              type="text"
              required
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="Contoh: Diskaun Akhir Minggu 30% Netflix"
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-pink-500"
            />
          </div>

          <div>
            <label className="block text-slate-300 font-medium mb-1">Sasaran Penerima (Audience)</label>
            <select
              value={audience}
              onChange={e => setAudience(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-pink-500"
            >
              <option value="All Active Users">Semua Pengguna Aktif Telegram ({customerCount || 1480} orang)</option>
              <option value="Paying Customers Only">Pelanggan Yang Pernah Membeli Sahaja</option>
              <option value="AI Studio Users">Pengguna Berry AI Studio Sahaja</option>
            </select>
          </div>

          <div>
            <label className="block text-slate-300 font-medium mb-1">
              Kandungan Mesej (Menyokong emoji & format Telegram)
            </label>
            <textarea
              rows={6}
              required
              value={message}
              onChange={e => setMessage(e.target.value)}
              placeholder="🍓 Promosi Hebat Berry Store!&#10;&#10;Dapatkan akaun Netflix & Spotify dengan diskaun RM5 harini sahaja.&#10;Gunakan butang /start untuk mula membeli!"
              className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-slate-100 focus:outline-none focus:border-pink-500 font-sans leading-relaxed"
            />
          </div>

          <div className="pt-2 flex items-center justify-between border-t border-slate-800">
            <span className="text-[11px] text-slate-400">
              Kadar kelajuan: Mengikut had rasmi Telegram API (~30 mesej/saat)
            </span>
            <button
              type="submit"
              disabled={isSending}
              className="px-5 py-2.5 bg-gradient-to-r from-pink-600 to-purple-600 hover:from-pink-500 hover:to-purple-500 text-white font-semibold rounded-xl transition-all cursor-pointer shadow-md shadow-pink-600/30 flex items-center gap-1.5 disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" />
              <span>{isSending ? 'Menghantar...' : 'Hantar Siaran Sekarang'}</span>
            </button>
          </div>
        </form>

        {/* Live Telegram Message Preview */}
        <div className="lg:col-span-2">
          <div className="bg-slate-950 border border-slate-800 rounded-3xl p-4 shadow-2xl space-y-3 font-sans">
            <div className="text-xs font-semibold text-slate-400 pb-2 border-b border-slate-800 flex items-center justify-between">
              <span>Pratonton Peti Mesej Pelanggan</span>
              <span className="text-pink-400 font-mono text-[10px]">Telegram Mobile</span>
            </div>

            <div className="bg-slate-900 rounded-2xl p-3.5 border border-slate-800 text-xs space-y-2">
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2 h-2 rounded-full bg-pink-500" />
                <span className="font-bold text-white text-xs">Berry Store Bot</span>
              </div>
              <div className="text-slate-200 whitespace-pre-line leading-relaxed text-xs">
                {message.trim() || 'Mesej anda akan dipaparkan di sini seperti mana ia muncul di Telegram pelanggan...'}
              </div>
              <div className="text-[10px] text-slate-400 text-right pt-1 font-mono">
                {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} ✓✓
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Broadcast History Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
        <div className="p-4 border-b border-slate-800">
          <h3 className="text-sm font-semibold text-white">Sejarah Kempen Siaran</h3>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 text-slate-400 uppercase font-mono tracking-wider border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">Tajuk Kempen</th>
                <th className="px-4 py-3">Sasaran</th>
                <th className="px-4 py-3 text-center">Status</th>
                <th className="px-4 py-3 text-right">Berjaya</th>
                <th className="px-4 py-3 text-right">Gagal / Disekat</th>
                <th className="px-4 py-3 text-right">Masa Dihantar</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-200">
              {broadcasts.map(bc => (
                <tr key={bc.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-3 font-semibold text-white">
                    {bc.title}
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {bc.audience}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded font-mono text-[10px]">
                      {bc.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-emerald-400 tabular-nums font-semibold">
                    {bc.success_count}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-400 tabular-nums">
                    {bc.failed_count || 0}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-400 text-[11px]">
                    {new Date(bc.sent_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
