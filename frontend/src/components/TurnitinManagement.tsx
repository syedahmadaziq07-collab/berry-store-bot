import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api';
import { FileText, RefreshCw, Save, ShieldCheck, Clock3, Package } from 'lucide-react';

type Code = 'similarity' | 'ai';
type Plan = {
  code: Code;
  title: string;
  description: string;
  price_myr: string | number;
  stock: number;
  enabled: boolean;
  turnaround_minutes: number;
};
type Job = {
  order_id: string;
  plan: Code;
  state: string;
  user_id: number;
  created_at?: string | null;
  submitted_at?: string | null;
  delivered_at?: string | null;
  has_assignment?: boolean;
};
type ResponseData = { plans: Plan[]; jobs: Job[] };

export const TurnitinManagement: React.FC<{ canEdit: boolean }> = ({ canEdit }) => {
  const [plans, setPlans] = useState<Record<string, Plan>>({});
  const [jobs, setJobs] = useState<Job[]>([]);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState<Code | null>(null);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  const refresh = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const res = await apiFetch('/api/admin/v1/turnitin');
      const data: ResponseData = await res.json();
      if (!Array.isArray(data?.plans) || !Array.isArray(data?.jobs)) {
        throw new Error('Backend Turnitin belum tersedia');
      }
      setPlans(Object.fromEntries(data.plans.map(p => [p.code, {
        ...p, price_myr: String(p.price_myr), stock: Number(p.stock),
        turnaround_minutes: Number(p.turnaround_minutes),
      }])));
      setJobs(data.jobs);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Turnitin service unavailable');
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const patch = (code: Code, key: keyof Plan, value: string | boolean | number) => {
    setPlans(previous => ({ ...previous,
      [code]: { ...previous[code], [key]: value },
    }));
  };

  const save = async (code: Code) => {
    if (!canEdit || !plans[code]) return;
    setSaving(code);
    setInfo('');
    setError('');
    const p = plans[code];
    try {
      const payload = {
        title: p.title.trim(), description: p.description.trim(),
        price_myr: String(p.price_myr), stock: Number(p.stock),
        enabled: p.enabled, turnaround_minutes: Number(p.turnaround_minutes),
      };
      const res = await apiFetch('/api/admin/v1/turnitin/plans/' + code, {
        method: 'PATCH', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      const confirmed = await res.json();
      if (confirmed.status !== 'committed' && confirmed.status !== 'replayed') {
        throw new Error('Pengesahan transaksi belum diterima');
      }
      setInfo(code.toUpperCase() + ' telah disimpan dalam database.');
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Gagal simpan');
    } finally {
      setSaving(null);
    }
  };

  const names: { code: Code; label: string; description: string }[] = [
    {code: 'similarity', label: 'Similarity Check', description: 'Manual similarity report fulfilment'},
    {code: 'ai', label: 'AI Writing Check', description: 'Manual AI writing indicator report'},
  ];

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl md:text-2xl font-semibold text-white flex items-center gap-2">
            <FileText className="w-6 h-6 text-pink-400" /> Turnitin Services
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Harga, stock, description, turnaround dan manual report orders.
          </p>
        </div>
        <button type="button" onClick={() => void refresh()} disabled={busy}
          className="px-3 py-2 text-sm bg-slate-800 rounded-lg border border-slate-700 flex gap-2 items-center disabled:opacity-40">
          <RefreshCw className={'w-4 h-4 ' + (busy ? 'animate-spin' : '')} /> Refresh
        </button>
      </div>

      <div className="rounded-xl border border-amber-800/60 bg-amber-950/20 px-4 py-3 text-xs text-amber-200 space-y-1">
        <p><strong>Manual fulfilment:</strong> Tiada API Turnitin rasmi atau automatic scan yang disambungkan.</p>
        <p>Loading di Telegram ialah timer anggaran (+1% setiap 30 saat; maksimum 99% sehingga PDF dihantar).</p>
        {!canEdit && <p><strong>Read-only:</strong> Editing dikunci sehingga backend isolated/write gate diaudit dan diaktifkan.</p>}
      </div>

      {error && <p role="alert" className="p-3 rounded-lg bg-red-950/30 border border-red-800 text-red-300 text-sm">{error}</p>}
      {info && <p role="status" className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-800 text-emerald-300 text-sm">{info}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        {names.map(item => {
          const plan = plans[item.code];
          return (
            <section key={item.code} className="p-4 md:p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-4">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <h2 className="font-semibold text-white">{item.label}</h2>
                  <p className="text-xs text-slate-400">{item.description}</p>
                </div>
                <span className={'text-xs rounded-full px-2 py-1 ' + (plan?.enabled ? 'bg-emerald-900 text-emerald-300' : 'bg-slate-800 text-slate-400')}>
                  {plan?.enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
              {!plan ? <p className="text-sm text-slate-500">Plan belum disediakan dalam backend.</p> : <>
                <label className="text-xs text-slate-300 block space-y-1">Nama servis
                  <input value={plan.title} onChange={e => patch(item.code, 'title', e.target.value)}
                    disabled={!canEdit} className="mt-1 w-full p-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white disabled:opacity-60" />
                </label>
                <label className="text-xs text-slate-300 block space-y-1">Description
                  <textarea rows={4} value={plan.description} onChange={e => patch(item.code, 'description', e.target.value)}
                    disabled={!canEdit} className="mt-1 w-full p-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white disabled:opacity-60 resize-y" />
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <label className="text-xs text-slate-300">Harga (RM)
                    <input type="number" min="0" max="9999" step="0.01" value={plan.price_myr}
                      onChange={e => patch(item.code, 'price_myr', e.target.value)} disabled={!canEdit}
                      className="mt-1 w-full p-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white disabled:opacity-60" />
                  </label>
                  <label className="text-xs text-slate-300 flex flex-col">Stock
                    <span className="relative"><Package className="absolute left-2 top-3 w-4 h-4 text-slate-500" />
                      <input type="number" min="0" max="100000" step="1" value={plan.stock}
                        onChange={e => patch(item.code, 'stock', Number(e.target.value))} disabled={!canEdit}
                        className="mt-1 w-full py-2 pl-8 pr-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white disabled:opacity-60" />
                    </span>
                  </label>
                  <label className="text-xs text-slate-300 col-span-2 flex items-center gap-2">
                    <Clock3 className="w-4 h-4" /> Anggaran turnaround (minit)
                    <input type="number" min="1" max="1440" step="1" value={plan.turnaround_minutes}
                      onChange={e => patch(item.code, 'turnaround_minutes', Number(e.target.value))} disabled={!canEdit}
                      className="ml-auto w-20 p-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white disabled:opacity-60" />
                  </label>
                </div>
                <label className="text-sm text-slate-300 flex gap-2 items-center">
                  <input type="checkbox" checked={plan.enabled} disabled={!canEdit}
                    onChange={e => patch(item.code, 'enabled', e.target.checked)}
                    className="accent-pink-500" /> Aktifkan servis ini (stock &amp; harga perlu tersedia)
                </label>
                <button type="button" disabled={!canEdit || saving !== null}
                  onClick={() => void save(item.code)}
                  className="w-full py-2.5 rounded-lg bg-pink-600 hover:bg-pink-500 font-semibold text-sm text-white disabled:opacity-40 flex gap-2 items-center justify-center">
                  <Save className="w-4 h-4" /> {saving === item.code ? 'Saving...' : 'Save Plan'}
                </button>
              </>}
            </section>
          );
        })}
      </div>

      <section className="rounded-xl bg-slate-900 border border-slate-800 overflow-x-auto">
        <div className="p-4 border-b border-slate-800 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-pink-400" />
          <h2 className="font-semibold text-white">Manual Report Orders</h2>
          <span className="text-xs text-slate-500 ml-auto">Metadata only — no private documents exposed</span>
        </div>
        <table className="w-full text-sm">
          <thead className="text-slate-400 text-xs bg-slate-950/60">
            <tr><th className="text-left px-4 py-3">Order ID</th><th className="text-left px-4 py-3">Service</th><th className="text-left px-4 py-3">Status</th><th className="text-left px-4 py-3">Received</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {jobs.map(j => <tr key={j.order_id}>
              <td className="px-4 py-3 font-mono text-xs text-slate-200">{j.order_id}</td>
              <td className="px-4 py-3">{j.plan}</td>
              <td className="px-4 py-3 capitalize">{j.state.replace(/_/g, ' ')}</td>
              <td className="px-4 py-3">{j.has_assignment ? '📎 Assignment received' : '—'}</td>
            </tr>)}
            {jobs.length === 0 && <tr><td colSpan={4} className="text-center py-8 text-slate-500">Tiada order Turnitin lagi.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
};
