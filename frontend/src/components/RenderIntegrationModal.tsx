import React, { useState } from 'react';
import {
  X,
  Server,
  CloudUpload,
  CheckCircle2,
  Copy,
  ExternalLink,
  ShieldCheck,
  FileCode,
  Terminal,
} from 'lucide-react';

interface RenderIntegrationModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const RenderIntegrationModal: React.FC<RenderIntegrationModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const renderConfigYaml = `# Separate staging service only
buildCommand: pip install -r requirements-admin.txt && npm --prefix frontend ci && npm --prefix frontend run build
startCommand: gunicorn --workers 1 --threads 4 --bind 0.0.0.0:$PORT 'admin_app:create_app()'
# ADMIN_PASSWORD_HASH, SUPABASE_URL, SUPABASE_SERVICE_KEY, TENANT_ID are server-only settings.
# ADMIN_WRITES_ENABLED=false; ADMIN_ISOLATED_DATABASE=false
# Never run bot.py on this staging service.`;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-pink-500/20 text-pink-400 rounded-xl">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white font-display">
                Konfigurasi Dashboard Staging
              </h3>
              <p className="text-xs text-slate-400">
                Perkhidmatan Render: <strong className="text-pink-400">berry-gemini-admin-staging</strong>
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-4 text-xs">
          {/* Status Banner */}
          <div className="bg-emerald-950/40 border border-emerald-800/60 rounded-xl p-3.5 flex items-start gap-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-emerald-300">
                Staging berasingan; production memerlukan kelulusan
              </div>
              <p className="text-slate-300 mt-0.5 leading-relaxed">
                Semak status backend melalui menu Pemantauan Sistem.
                Sambungan database belum disahkan sehingga ujian bacaan data sebenar lulus.
              </p>
            </div>
          </div>

          {/* Render Environment Variables Checklist */}
          <div>
            <h4 className="font-bold text-white text-xs mb-2 flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-pink-400" />
              <span>Pemboleh Ubah Persekitaran Render (Environment Variables)</span>
            </h4>
            <div className="bg-slate-950 rounded-xl border border-slate-800 divide-y divide-slate-800/60 font-mono text-[11px]">
              <div className="p-2.5 flex items-center justify-between">
                <div>
                  <span className="text-pink-400 font-bold">ADMIN_PASSWORD_HASH</span>
                  <div className="text-[10px] text-slate-400 font-sans">Hash kata laluan admin (server sahaja)</div>
                </div>
                <span className="text-emerald-400 font-sans">Wajib Rahsia (Render Secret)</span>
              </div>
              <div className="p-2.5 flex items-center justify-between">
                <div>
                  <span className="text-pink-400 font-bold">SUPABASE_URL</span>
                  <div className="text-[10px] text-slate-400 font-sans">https://gtqthdxltczovkiuoyyr.supabase.co</div>
                </div>
                <span className="text-slate-300 font-sans">Public Config</span>
              </div>
              <div className="p-2.5 flex items-center justify-between">
                <div>
                  <span className="text-pink-400 font-bold">SUPABASE_SERVICE_KEY</span>
                  <div className="text-[10px] text-slate-400 font-sans">Kunci service_role rahsia untuk akses lejar</div>
                </div>
                <span className="text-emerald-400 font-sans">Pelayan Sahaja</span>
              </div>
              <div className="p-2.5 flex items-center justify-between">
                <div>
                  <span className="text-pink-400 font-bold">TENANT_ID</span>
                  <div className="text-[10px] text-slate-400 font-sans">Tetapkan daripada konfigurasi tenant sebenar</div>
                </div>
                <span className="text-slate-300 font-sans">Tenant Scope</span>
              </div>
            </div>
          </div>

          {/* Render YAML Configuration Snippet */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <h4 className="font-bold text-white text-xs flex items-center gap-1.5">
                <FileCode className="w-4 h-4 text-purple-400" />
                <span>render.yaml Service Spec</span>
              </h4>
              <button
                type="button"
                onClick={() => handleCopy(renderConfigYaml, 'yaml')}
                className="text-pink-400 hover:text-pink-300 flex items-center gap-1 font-mono text-[11px] cursor-pointer"
              >
                <Copy className="w-3.5 h-3.5" />
                <span>{copiedKey === 'yaml' ? 'Disalin!' : 'Salin YAML'}</span>
              </button>
            </div>
            <pre className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-[11px] font-mono text-slate-300 overflow-x-auto leading-relaxed">
              {renderConfigYaml}
            </pre>
          </div>

          {/* Production Verification Checklist */}
          <div>
            <h4 className="font-bold text-white text-xs mb-2">Semakan Pasca-Deployment (Verification Steps)</h4>
            <ul className="space-y-1.5 text-slate-300 list-disc list-inside">
              <li>Buka dashboard melalui <code>https://berry-gemini-admin-staging.onrender.com/dashboard</code></li>
              <li>Log masuk hanya menggunakan kata laluan tunggal tanpa perlu menampal URL atau kunci Supabase di borang.</li>
              <li>Pastikan pesanan pending dan stok produk dikemaskini secara automatik pada bot Telegram.</li>
              <li>Uji kelulusan pesanan pembayaran manual untuk menghantar kredensial akaun secara automatik.</li>
            </ul>
          </div>

          <div className="pt-3 border-t border-slate-800 flex items-center justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-pink-600 hover:bg-pink-500 text-white rounded-xl font-semibold cursor-pointer"
            >
              Faham & Tutup
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
