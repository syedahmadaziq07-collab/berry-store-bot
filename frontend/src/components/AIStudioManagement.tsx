import React, { useState } from 'react';
import {
  Sparkles,
  Cpu,
  Video,
  Image as ImageIcon,
  Mic,
  Zap,
  CheckCircle2,
  AlertCircle,
  Save,
  Radio,
  ExternalLink,
} from 'lucide-react';
import { AITool, AIModel } from '../types/store';
import { formatMYR } from '../utils/store-logic';

interface AIStudioManagementProps {
  tools: AITool[];
  models: AIModel[];
  onUpdateTool: (id: string, updates: Partial<AITool>) => Promise<void>;
  onUpdateModel: (id: string, updates: Partial<AIModel>) => Promise<void>;
}

export const AIStudioManagement: React.FC<AIStudioManagementProps> = ({
  tools,
  models,
  onUpdateTool,
  onUpdateModel,
}) => {
  const [activeTab, setActiveTab] = useState<'tools' | 'models'>('tools');
  const [testingModelId, setTestingModelId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ id: string; success: boolean; latency: number } | null>(null);

  const handleTestConnection = async (model: AIModel) => {
    setTestingModelId(model.id);
    setTestResult(null);
    try {
      const response = await fetch(`/api/admin/v1/ai/models/${encodeURIComponent(model.id)}/health`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Provider belum diuji');
      setTestResult({id: model.id, success: data.status === 'ok', latency: data.latency});
    } catch (error: any) {
      window.dispatchEvent(new CustomEvent('api-error', {detail: error.message}));
    } finally { setTestingModelId(null); }
  };

  return (
    <div className="space-y-6">
      {/* Header & Sub-Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold text-white font-display">Kawalan Berry AI Studio</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Konfigurasi alat penjanaan video/imej AI di Telegram, caj kredit MYR & katalog pembekal fal.ai
          </p>
        </div>

        {/* Tab Controls */}
        <div className="flex items-center bg-slate-900 border border-slate-800 p-1 rounded-xl">
          <button
            type="button"
            onClick={() => setActiveTab('tools')}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer flex items-center gap-1.5 ${
              activeTab === 'tools' ? 'bg-pink-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Alatan AI Telegram ({tools.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('models')}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer flex items-center gap-1.5 ${
              activeTab === 'models' ? 'bg-pink-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>Katalog Model & Margin ({models.length})</span>
          </button>
        </div>
      </div>

      {/* AI TOOLS TAB */}
      {activeTab === 'tools' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {tools.map(tool => (
            <div
              key={tool.id}
              className={`bg-slate-900 border rounded-2xl p-5 flex flex-col justify-between transition-all ${
                tool.enabled ? 'border-slate-800' : 'border-slate-800/50 opacity-70'
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 bg-gradient-to-tr from-pink-500/20 to-purple-500/20 text-pink-400 rounded-xl border border-pink-500/30">
                      {tool.category === 'video' ? <Video className="w-4 h-4" /> : tool.category === 'image' ? <ImageIcon className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
                    </div>
                    <div>
                      <h3 className="font-bold text-white text-sm">{tool.name}</h3>
                      <div className="text-[11px] text-slate-400 font-mono">ID: {tool.model_id}</div>
                    </div>
                  </div>

                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={tool.enabled}
                      onChange={e => onUpdateTool(tool.id, { enabled: e.target.checked })}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-pink-600"></div>
                  </label>
                </div>

                <p className="text-xs text-slate-300 mb-4">{tool.description}</p>

                {/* Parameters & Pricing */}
                <div className="grid grid-cols-2 gap-3 text-xs bg-slate-950 p-3 rounded-xl border border-slate-800 mb-4">
                  <div>
                    <span className="text-slate-400 text-[10px] block">Caj Kredit Pengguna</span>
                    <div className="font-mono font-bold text-pink-400 text-sm mt-0.5">
                      {formatMYR(tool.credit_cost)} / job
                    </div>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[10px] block">Had Harian Pengguna</span>
                    <div className="font-mono font-bold text-white text-sm mt-0.5">
                      {tool.daily_limit_per_user} kali/hari
                    </div>
                  </div>
                </div>

                {tool.supported_ratios && tool.supported_ratios.length > 0 && (
                  <div className="flex items-center gap-1.5 text-[11px] text-slate-400 mb-2">
                    <span>Nisbah Aspek:</span>
                    {tool.supported_ratios.map(r => (
                      <span key={r} className="bg-slate-800 px-1.5 py-0.5 rounded text-slate-200 font-mono text-[10px]">
                        {r}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Maintenance Toggle */}
              <div className="pt-3 border-t border-slate-800 flex items-center justify-between text-xs">
                <span className="text-slate-400">Status Penyelenggaraan:</span>
                <button
                  type="button"
                  onClick={() => onUpdateTool(tool.id, { maintenance: !tool.maintenance })}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold cursor-pointer border ${
                    tool.maintenance
                      ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                      : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                  }`}
                >
                  {tool.maintenance ? 'Under Maintenance' : 'Operational'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* AI MODEL CATALOG & MARGIN TAB */}
      {activeTab === 'models' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
          <div className="p-4 border-b border-slate-800 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white">Katalog Model & Pengiraan Margin Untung</h3>
              <p className="text-xs text-slate-400">Harga kos pembekal fal.ai vs harga jualan kredit Telegram kepada pelanggan</p>
            </div>
            <div className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-md border border-emerald-500/20">
              Purata Margin: {models.length ? `${(models.reduce((sum, m) => sum + m.margin_pct, 0) / models.length).toFixed(1)}%` : 'Belum tersedia'}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/60 text-slate-400 uppercase font-mono tracking-wider border-b border-slate-800">
                <tr>
                  <th className="px-4 py-3">Nama Model & ID</th>
                  <th className="px-4 py-3">Pembekal</th>
                  <th className="px-4 py-3 text-right">Kos Pembekal (RM)</th>
                  <th className="px-4 py-3 text-right">Harga Jual (RM)</th>
                  <th className="px-4 py-3 text-center">Margin %</th>
                  <th className="px-4 py-3 text-center">Status</th>
                  <th className="px-4 py-3 text-right">Uji Sambungan</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-200">
                {models.map(m => (
                  <tr key={m.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-semibold text-white">{m.name}</div>
                      <div className="text-[11px] text-pink-400 font-mono">{m.model_id}</div>
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-300">
                      <span className="bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                        {m.provider}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-slate-400 tabular-nums">
                      {formatMYR(m.provider_cost)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-bold text-pink-400 tabular-nums">
                      {formatMYR(m.customer_price)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className="bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded font-mono font-bold">
                        +{m.margin_pct}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        type="button"
                        onClick={() => onUpdateModel(m.id, { enabled: !m.enabled })}
                        className="cursor-pointer"
                        title={m.enabled ? 'Nyahaktifkan' : 'Aktifkan'}
                      >
                        {m.enabled ? (
                          <span className="text-emerald-400 font-medium inline-flex items-center gap-1">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            <span>Aktif</span>
                          </span>
                        ) : (
                          <span className="text-slate-400 inline-flex items-center gap-1">
                            <span>Mati</span>
                          </span>
                        )}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {testResult?.id === m.id && (
                          <span className="text-emerald-400 font-mono text-[10px]">
                            {testResult.latency}ms OK
                          </span>
                        )}
                        <button
                          type="button"
                          disabled={testingModelId === m.id}
                          onClick={() => handleTestConnection(m)}
                          className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-1"
                        >
                          <Zap className={`w-3 h-3 ${testingModelId === m.id ? 'animate-bounce text-pink-400' : ''}`} />
                          <span>{testingModelId === m.id ? 'Menguji...' : 'Ping Test'}</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
