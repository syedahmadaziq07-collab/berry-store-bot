import React, { useState } from 'react';
import {
  Bot,
  Save,
  Image,
  AlertTriangle,
  QrCode,
  Sparkles,
  ShoppingBag,
  ExternalLink,
  MessageSquare,
  ShieldAlert,
  Send,
  HelpCircle,
} from 'lucide-react';
import { BotSettings } from '../types/store';

interface TelegramBotControlProps {
  settings: BotSettings;
  onSaveSettings: (updates: Partial<BotSettings>) => Promise<void>;
}

export const TelegramBotControl: React.FC<TelegramBotControlProps> = ({
  settings,
  onSaveSettings,
}) => {
  const [formData, setFormData] = useState<BotSettings>({ ...settings });
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const handleChange = (key: string, value: string) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  const handleToggle = (key: string) => {
    const current = formData[key] === 'true';
    setFormData(prev => ({ ...prev, [key]: current ? 'false' : 'true' }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSaveSuccess(false);
    try {
      await onSaveSettings(formData);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold text-white font-display">Pusat Kawalan Bot Telegram</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Semua perubahan disimpan terus ke jadual bot_settings Supabase dan mempengaruhi tingkah laku bot.py sebenar
          </p>
        </div>

        <button
          type="button"
          onClick={handleSubmit}
          disabled={isSaving}
          className="px-4 py-2 bg-pink-600 hover:bg-pink-500 text-white text-xs font-semibold rounded-xl flex items-center gap-1.5 transition-colors cursor-pointer self-start sm:self-auto shadow-md shadow-pink-600/20 disabled:opacity-50"
        >
          <Save className="w-3.5 h-3.5" />
          <span>{isSaving ? 'Menyimpan ke Supabase...' : 'Simpan Semua Tetapan'}</span>
        </button>
      </div>

      {saveSuccess && (
        <div className="p-3 bg-emerald-950/60 border border-emerald-800/80 rounded-xl text-emerald-300 text-xs flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-emerald-400" />
          <span>Tetapan bot berjaya disimpan dan dimuat semula ke Telegram cache!</span>
        </div>
      )}

      {/* Main Settings & Simulator Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Settings Form Column (3 cols) */}
        <form onSubmit={handleSubmit} className="lg:col-span-3 space-y-5">
          {/* Feature Master Switches */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4 shadow-lg">
            <h3 className="text-sm font-semibold text-white border-b border-slate-800 pb-2">
              Suis Utama Modul Telegram
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
              {/* Maintenance Mode */}
              <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 flex items-center justify-between">
                <div>
                  <div className="font-semibold text-white">Mod Penyelenggaraan</div>
                  <div className="text-[11px] text-slate-400">Halang pelanggan dari membuat pesanan baru</div>
                </div>
                <button
                  type="button"
                  onClick={() => handleToggle('maintenance_mode')}
                  className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors cursor-pointer ${
                    formData.maintenance_mode === 'true' ? 'bg-amber-600' : 'bg-slate-800'
                  }`}
                >
                  <div
                    className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${
                      formData.maintenance_mode === 'true' ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>

              {/* Browse Shop */}
              <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 flex items-center justify-between">
                <div>
                  <div className="font-semibold text-white">Browse Shop</div>
                  <div className="text-[11px] text-slate-400">Aktifkan butang senarai kedai digital</div>
                </div>
                <button
                  type="button"
                  onClick={() => handleToggle('browse_shop_enabled')}
                  className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors cursor-pointer ${
                    formData.browse_shop_enabled === 'true' ? 'bg-pink-600' : 'bg-slate-800'
                  }`}
                >
                  <div
                    className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${
                      formData.browse_shop_enabled === 'true' ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>

              {/* AI Studio */}
              <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 flex items-center justify-between">
                <div>
                  <div className="font-semibold text-white">Berry AI Studio</div>
                  <div className="text-[11px] text-slate-400">Alatan jana video & gambar fal.ai</div>
                </div>
                <button
                  type="button"
                  onClick={() => handleToggle('ai_studio_enabled')}
                  className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors cursor-pointer ${
                    formData.ai_studio_enabled === 'true' ? 'bg-pink-600' : 'bg-slate-800'
                  }`}
                >
                  <div
                    className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${
                      formData.ai_studio_enabled === 'true' ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>

              {/* Referrals */}
              <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 flex items-center justify-between">
                <div>
                  <div className="font-semibold text-white">Program Rujukan (Referral)</div>
                  <div className="text-[11px] text-slate-400">Ganjaran kredit mengajak rakan</div>
                </div>
                <button
                  type="button"
                  onClick={() => handleToggle('referral_enabled')}
                  className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors cursor-pointer ${
                    formData.referral_enabled === 'true' ? 'bg-pink-600' : 'bg-slate-800'
                  }`}
                >
                  <div
                    className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${
                      formData.referral_enabled === 'true' ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>
            </div>
          </div>

          {/* Texts & Announcements */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4 shadow-lg text-xs">
            <h3 className="text-sm font-semibold text-white border-b border-slate-800 pb-2">
              Mesej Selamat Datang & Pengumuman
            </h3>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Mesej Sambutan /start</label>
              <textarea
                rows={4}
                value={formData.welcome_message || ''}
                onChange={e => handleChange('welcome_message', e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-slate-100 focus:outline-none focus:border-pink-500 font-sans"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Pengumuman Terkini (Banner Promo)</label>
              <input
                type="text"
                value={formData.announcement || ''}
                onChange={e => handleChange('announcement', e.target.value)}
                placeholder="Pengumuman ringkas yang muncul di menu utama..."
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-pink-500"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Saluran Wajib Join</label>
                <input
                  type="text"
                  value={formData.required_channel || ''}
                  onChange={e => handleChange('required_channel', e.target.value)}
                  placeholder="@berrystorrel"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 font-mono focus:outline-none focus:border-pink-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Pautan Bantuan (Support Handle)</label>
                <input
                  type="text"
                  value={formData.support_username || ''}
                  onChange={e => handleChange('support_username', e.target.value)}
                  placeholder="@berrystoresupport"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 font-mono focus:outline-none focus:border-pink-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-slate-300 font-medium mb-1">URL Banner Bot</label>
                <input
                  type="text"
                  value={formData.banner_url || ''}
                  onChange={e => handleChange('banner_url', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 font-mono text-[11px] focus:outline-none focus:border-pink-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">URL Kod QR DuitNow</label>
                <input
                  type="text"
                  value={formData.payment_qr_url || ''}
                  onChange={e => handleChange('payment_qr_url', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 font-mono text-[11px] focus:outline-none focus:border-pink-500"
                />
              </div>
            </div>
          </div>
        </form>

        {/* Live Telegram Chat Simulator Column (2 cols) */}
        <div className="lg:col-span-2">
          <div className="sticky top-20 bg-slate-950 border border-slate-800 rounded-3xl p-4 shadow-2xl space-y-3 font-sans">
            {/* Telegram Header */}
            <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-pink-600 flex items-center justify-center text-white text-xs font-bold">
                  🍓
                </div>
                <div>
                  <div className="font-bold text-white leading-tight">Berry Store Bot</div>
                  <div className="text-[10px] text-emerald-400">online</div>
                </div>
              </div>
              <span className="text-[10px] text-slate-400 font-mono">Live Sync</span>
            </div>

            {/* Banner Image */}
            <div className="rounded-xl overflow-hidden border border-slate-800">
              <img
                src={formData.banner_url || '/images/berry_store_banner_1794372741684.jpg'}
                alt="Banner"
                className="w-full h-32 object-cover"
              />
            </div>

            {/* Announcement Badge */}
            {formData.announcement && (
              <div className="bg-amber-500/10 border border-amber-500/20 text-amber-300 text-[11px] p-2 rounded-xl">
                {formData.announcement}
              </div>
            )}

            {/* Welcome Text Bubble */}
            <div className="bg-slate-900 rounded-2xl p-3 border border-slate-800 text-xs text-slate-200 whitespace-pre-line leading-relaxed">
              {formData.welcome_message}
            </div>

            {/* Inline Keyboard Simulation */}
            <div className="space-y-1.5 pt-1">
              {formData.browse_shop_enabled === 'true' && (
                <button
                  type="button"
                  className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-2 border border-slate-700 transition-colors"
                >
                  <ShoppingBag className="w-3.5 h-3.5 text-pink-400" />
                  <span>🛒 Beli Akaun Premium</span>
                </button>
              )}

              {formData.ai_studio_enabled === 'true' && (
                <button
                  type="button"
                  className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-2 border border-slate-700 transition-colors"
                >
                  <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                  <span>🎨 Berry AI Studio</span>
                </button>
              )}

              <div className="grid grid-cols-2 gap-1.5">
                <button
                  type="button"
                  className="py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-medium border border-slate-700 transition-colors"
                >
                  💰 Dompet Saya
                </button>

                {formData.referral_enabled === 'true' ? (
                  <button
                    type="button"
                    className="py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-medium border border-slate-700 transition-colors"
                  >
                    👥 Ganjaran Rujukan
                  </button>
                ) : (
                  <button
                    type="button"
                    className="py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-medium border border-slate-700 transition-colors"
                  >
                    ℹ️ Bantuan
                  </button>
                )}
              </div>

              <button
                type="button"
                className="w-full py-2 bg-slate-900 hover:bg-slate-800 text-pink-400 rounded-xl text-xs font-semibold border border-pink-500/30 transition-colors"
              >
                💬 Hubungi Bantuan ({formData.support_username || '@support'})
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
