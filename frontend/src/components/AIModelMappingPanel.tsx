import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';

type ToolKey = 'image' | 'video' | 'transform' | 'voice' | 'enhance' | 'storyboard';
type Mapping = {
  tool_key: ToolKey;
  display_name: string;
  provider_model_id: string;
  credit_cost: number;
  enabled: boolean;
};
const TOOL_OPTIONS: ToolKey[] = ['image', 'video', 'transform', 'voice', 'enhance', 'storyboard'];
const BASE = '/api/admin/v1/ai/model-mappings';

export function AIModelMappingPanel() {
  const [items, setItems] = useState<Mapping[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [mode, setMode] = useState<'staging-draft-only' | 'private-persistent-staging'>('staging-draft-only');
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let active = true;
    apiFetch(BASE).then(async response => {
      const data = await response.json();
      if (active) {
        if (!Array.isArray(data)) throw new Error('Format mapping tidak sah');
        setItems(data);
        setMode(response.headers.get('X-Berry-Mapping-Mode') === 'private-persistent-staging' ? 'private-persistent-staging' : 'staging-draft-only');
        setRevision(Number(response.headers.get('X-Berry-Mapping-Revision') || 0));
      }
    }).catch(e => { if (active) setError(String(e.message)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const update = (idx: number, changes: Partial<Mapping>) =>
    setItems(old => old.map((item, i) => i === idx ? {...item, ...changes} : item));

  const add = () => {
    const key = TOOL_OPTIONS.find(name => !items.some(item => item.tool_key === name));
    if (!key) return setError('Semua 6 jenis alat sudah dikonfigurasi.');
    setItems(old => [...old, {tool_key: key, display_name: '', provider_model_id: '',
      credit_cost: 0, enabled: false}]);
    setError('');
  };

  async function save() {
    setError('');
    setNotice('');
    setSaving(true);
    try {
      const result = await apiFetch(BASE, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json', 'X-Berry-Mapping-Revision': String(revision)},
        body: JSON.stringify(items),
      });
      const payload = await result.json();
      if (!Array.isArray(payload)) throw new Error('Respons simpanan tidak sah');
      setItems(payload);
      const nextMode = result.headers.get('X-Berry-Mapping-Mode') === 'private-persistent-staging' ? 'private-persistent-staging' : 'staging-draft-only';
      setMode(nextMode);
      setRevision(Number(result.headers.get('X-Berry-Mapping-Revision') || 0));
      setNotice(nextMode === 'private-persistent-staging'
        ? 'Mapping disimpan dalam private staging database. Telegram bot dan fal.ai belum diaktifkan.'
        : 'Draft disimpan pada SQLite staging sementara; boleh hilang selepas restart.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Simpanan gagal');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-bold text-white">Nama Telegram ≠ Model Sebenar</h2>
          <p className="text-xs text-slate-400 mt-1">
            Staging sahaja: nama paparan berasingan daripada Provider Model ID fal.ai.
            {mode === 'private-persistent-staging' ? ' Mapping disimpan dalam database ujian private.' : ' Draft SQLite sementara boleh hilang selepas redeploy.'}
            {' '}Belum mengaktifkan bot, AI generation atau caj Berry Credits.
          </p>
        </div>
        <button type="button" onClick={add} disabled={loading}
          className="rounded-lg bg-slate-800 text-white px-3 py-2 text-xs disabled:opacity-50">
          + Tambah Mapping
        </button>
      </div>
      {loading && <p className="text-sm text-slate-400">Memuatkan mapping daripada server...</p>}
      {error && <p role="alert" className="text-xs text-red-300 bg-red-950/40 rounded p-2">{error}</p>}
      {notice && <p role="status" className="text-xs text-emerald-300">{notice}</p>}
      {!loading && items.length === 0 && (
        <p className="text-xs text-slate-400">Belum ada mapping. Tambah model untuk mula konfigurasi.</p>
      )}
      {items.map((item, index) => (
        <div key={item.tool_key} className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3 border border-slate-700 rounded-xl p-3">
          <label className="text-xs text-slate-300">Fungsi Telegram
            <select value={item.tool_key} onChange={e => update(index, {tool_key: e.target.value as ToolKey})}
              className="block w-full mt-1 bg-slate-950 border border-slate-700 rounded p-2 text-white">
              {TOOL_OPTIONS.map(key => <option key={key} disabled={items.some((m, i) => i !== index && m.tool_key === key)} value={key}>{key}</option>)}
            </select>
          </label>
          <label className="text-xs text-slate-300">Display Name (Telegram)
            <input value={item.display_name} maxLength={64}
              onChange={e => update(index, {display_name: e.target.value})}
              placeholder="Berry Image Pro" className="block w-full mt-1 bg-slate-950 border border-slate-700 rounded p-2 text-white" />
          </label>
          <label className="text-xs text-slate-300">Provider Model ID (server sahaja)
            <input value={item.provider_model_id} maxLength={160}
              onChange={e => update(index, {provider_model_id: e.target.value})}
              placeholder="fal-ai/flux/dev" autoComplete="off"
              className="block w-full mt-1 bg-slate-950 border border-slate-700 rounded p-2 text-white" />
          </label>
          <label className="text-xs text-slate-300">Caj Berry Credits / job (konfigurasi)
            <input type="number" min={0} max={1000000} step={1} value={item.credit_cost}
              onChange={e => update(index, {credit_cost: Number(e.target.value)})}
              className="block w-full mt-1 bg-slate-950 border border-slate-700 rounded p-2 text-white" />
          </label>
          <div className="flex items-center justify-between gap-2 text-xs text-slate-300">
            <label className="flex gap-2 items-center"><input type="checkbox" checked={item.enabled}
              onChange={e => update(index, {enabled: e.target.checked})} />Tunjuk nama</label>
            <button type="button" className="text-red-300 underline"
              onClick={() => setItems(old => old.filter((_, i) => i !== index))}>Buang</button>
          </div>
        </div>
      ))}
      <button type="button" onClick={save} disabled={saving || loading}
        className="px-4 py-2 bg-pink-600 hover:bg-pink-500 rounded-lg text-white text-xs disabled:opacity-50">
        {saving ? 'Menyimpan...' : 'Simpan Mapping'}
      </button>
      <p className="text-[11px] text-amber-300">{mode === "private-persistent-staging" ? "Mapping disimpan pada private database staging berasingan." : "Simpanan hanya pada SQLite staging dan mungkin hilang semasa redeploy."} Tidak dikongsi dengan Telegram bot. Database production tidak disentuh.</p>
    </section>
  );
}
