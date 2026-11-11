import React, { useState } from 'react';
import {
  KeyRound,
  Plus,
  Trash2,
  Copy,
  Check,
  ShieldAlert,
  Sparkles,
  Upload,
  X,
} from 'lucide-react';
import { CredentialItem, Product } from '../types/store';

interface CredentialInventoryProps {
  credentials: CredentialItem[];
  products: Product[];
  onImportCredentials: (productId: string, variantId: string | null, rawCredentials: string) => Promise<void>;
  onDeleteCredential: (id: string) => Promise<void>;
}

export const CredentialInventory: React.FC<CredentialInventoryProps> = ({
  credentials,
  products,
  onImportCredentials,
  onDeleteCredential,
}) => {
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [selectedProductId, setSelectedProductId] = useState(products[0]?.id || '');
  const [selectedVariantId, setSelectedVariantId] = useState('');
  const [rawText, setRawText] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const selectedProduct = products.find(p => p.id === selectedProductId);

  const handleCopy = async (text: string, id: string) => {
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleImportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProductId || !rawText.trim()) return;
    await onImportCredentials(selectedProductId, selectedVariantId || null, rawText);
    setIsImportModalOpen(false);
    setRawText('');
  };

  const availableCount = credentials.filter(c => !c.is_used).length;
  const usedCount = credentials.filter(c => c.is_used).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold text-white font-display">Inventori Kredensial & Penghantaran Auto</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Semak metadata inventori. Penghantaran perlu disahkan melalui aliran pembayaran dan Telegram.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setIsImportModalOpen(true)}
          className="px-3.5 py-2 bg-pink-600 hover:bg-pink-500 text-white text-xs font-semibold rounded-xl flex items-center gap-1.5 transition-colors cursor-pointer self-start sm:self-auto shadow-md shadow-pink-600/20"
        >
          <Upload className="w-3.5 h-3.5" />
          <span>Import Pukal Kredensial</span>
        </button>
      </div>

      {/* KPI Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-xs text-slate-400">Jumlah Kredensial Tersedia (Ready)</div>
          <div className="text-2xl font-bold text-emerald-400 font-mono mt-1 tabular-nums">{availableCount}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Rekod inventori belum digunakan</div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-xs text-slate-400">Rekod Ditandakan Digunakan</div>
          <div className="text-2xl font-bold text-slate-300 font-mono mt-1 tabular-nums">{usedCount}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Status penggunaan daripada database</div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-xs text-slate-400">Keselamatan Data</div>
          <div className="text-sm font-semibold text-pink-400 mt-2 flex items-center gap-1.5">
            <ShieldAlert className="w-4 h-4" />
            <span>Paparan Topeng (Masked View)</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">Kredensial sulit dilindungi dari paparan umum</div>
        </div>
      </div>

      {/* Credentials Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 text-slate-400 uppercase font-mono tracking-wider border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">ID & Masa Ditambah</th>
                <th className="px-4 py-3">Produk Berkaitan</th>
                <th className="px-4 py-3">Kredensial Digital (Masked)</th>
                <th className="px-4 py-3 text-center">Status</th>
                <th className="px-4 py-3 text-right">Tindakan</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-200">
              {credentials.map(c => {
                const prod = products.find(p => p.id === c.product_id);
                return (
                  <tr key={c.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3 font-mono text-slate-400">
                      <div className="text-slate-300 font-semibold">{c.id}</div>
                      <div className="text-[10px]">{new Date(c.created_at).toLocaleDateString()}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-semibold text-white">{prod?.name || c.product_id}</div>
                      <div className="text-[10px] text-slate-400">{prod?.category}</div>
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-300">
                      <div className="bg-slate-950 px-2.5 py-1.5 rounded-lg border border-slate-800 inline-flex items-center gap-2 max-w-md truncate">
                        <span>{c.credential_data_masked || c.credential_data}</span>
                        <button
                          type="button"
                          disabled={!c.credential_data}
                          onClick={() => handleCopy(c.credential_data, c.id)}
                          className="p-1 hover:text-pink-400 transition-colors"
                          title={c.credential_data ? "Salin Kredensial" : "Credential dilindungi oleh server"}
                        >
                          {copiedId === c.id ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className={`inline-block px-2.5 py-0.5 rounded-md text-[11px] font-mono ${
                          c.is_used
                            ? 'bg-slate-800 text-slate-400'
                            : 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                        }`}
                      >
                        {c.is_used ? `Digunakan (${c.order_id || 'Delivered'})` : 'Tersedia'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {!c.is_used && (
                        <button
                          type="button"
                          onClick={() => onDeleteCredential(c.id)}
                          className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors cursor-pointer"
                          title="Padam"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* BULK IMPORT MODAL */}
      {isImportModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg p-6 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
              <h3 className="text-base font-bold text-white font-display">
                Import Pukal Kredensial Digital
              </h3>
              <button
                type="button"
                onClick={() => setIsImportModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleImportSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Pilih Produk Sasaran</label>
                <select
                  value={selectedProductId}
                  onChange={e => {
                    setSelectedProductId(e.target.value);
                    setSelectedVariantId('');
                  }}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-pink-500"
                >
                  {products.map(p => (
                    <option key={p.id} value={p.id}>{p.name} ({p.category})</option>
                  ))}
                </select>
              </div>

              {selectedProduct?.variants && selectedProduct.variants.length > 0 && (
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Pilih Varian (Pilihan)</label>
                  <select
                    value={selectedVariantId}
                    onChange={e => setSelectedVariantId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-pink-500"
                  >
                    <option value="">Semua Varian</option>
                    {selectedProduct.variants.map(v => (
                      <option key={v.id} value={v.id}>{v.variant_name}</option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Masukkan Kredensial (Satu baris untuk setiap satu akaun/kunci):
                </label>
                <textarea
                  rows={6}
                  required
                  value={rawText}
                  onChange={e => setRawText(e.target.value)}
                  placeholder="user1@berry.my | pass123 | pin: 1234&#10;user2@berry.my | pass456 | pin: 5678&#10;https://canva.com/invite/..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-slate-100 font-mono text-xs focus:outline-none focus:border-pink-500"
                />
                <p className="text-[11px] text-slate-400 mt-1">
                  Setiap baris mewakili 1 stok yang akan dihantar automatik oleh Telegram bot apabila bayaran diluluskan.
                </p>
              </div>

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsImportModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl cursor-pointer"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-pink-600 hover:bg-pink-500 text-white rounded-xl font-semibold cursor-pointer shadow-md"
                >
                  Sahkan & Tambah ke Inventori
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
