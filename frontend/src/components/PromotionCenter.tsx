import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';
import { Send, Link2, MessageCircle, CalendarDays, ListChecks, RefreshCw, Plus, CheckCircle2, AlertTriangle, ExternalLink } from 'lucide-react';

type Destination = {
  id: string; name: string; kind: 'telegram_group' | 'telegram_channel' | 'google_form';
  target_url: string; telegram_chat_id?: string; posting_permitted: boolean; active: boolean;
  form_email?: string | null; form_message_entry?: string | null; form_email_entry?: string | null;
  form_fixed_fields?: Record<string, string>;
  submission_mode?: 'manual' | 'auto'; auto_submit_authorized?: boolean;
};
type ThreadsAccount = { id: string; username: string; active: boolean; expires_at?: string | null };
type Campaign = { id: string; title: string; message: string; state: string; scheduled_for: string; created_at: string };
type Delivery = { id: string; campaign_id: string; destination_id?: string; threads_account_id?: string; state: string; external_id?: string | null; error_message?: string | null };
type Template = { id: string; name: string; message: string };
type PromotionState = { destinations: Destination[]; threads_accounts: ThreadsAccount[]; campaigns: Campaign[]; deliveries: Delivery[]; templates: Template[]; threads_configured: boolean; auto_form_submission: boolean };
type Connection = { connected: boolean; googleFormsAutoSubmit: boolean; maxThreadsAccounts: number };

const base = '/api/admin/v1/promotion';
const field = 'w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-pink-500';
const label = 'block text-xs font-medium text-slate-300 mb-1.5';
const panel = 'rounded-2xl border border-slate-800 bg-slate-900/80 p-4 md:p-5 space-y-4';
const primary = 'rounded-xl bg-pink-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-pink-500 disabled:cursor-not-allowed disabled:opacity-40';
const secondary = 'rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-100 hover:border-pink-500 disabled:opacity-40';

const date = (value?: string | null) => value ? new Date(value).toLocaleString('ms-MY', { dateStyle: 'medium', timeStyle: 'short' }) : '-';

export function PromotionCenter() {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [data, setData] = useState<PromotionState | null>(null);
  const [tab, setTab] = useState<'campaign' | 'destinations' | 'threads' | 'history'>('campaign');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [kind, setKind] = useState<Destination['kind']>('telegram_group');
  const [destinationName, setDestinationName] = useState('');
  const [destinationUrl, setDestinationUrl] = useState('');
  const [chatId, setChatId] = useState('');
  const [gmail, setGmail] = useState('');
  const [formMessageEntry, setFormMessageEntry] = useState('');
  const [formEmailEntry, setFormEmailEntry] = useState('');
  const [formMode, setFormMode] = useState<'manual'|'auto'>('manual');
  const [formAuthorized, setFormAuthorized] = useState(false);
  const [permitted, setPermitted] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingActive, setEditingActive] = useState(true);
  const [editingFixedFields, setEditingFixedFields] = useState<Record<string, string>>({});
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [schedule, setSchedule] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [captions, setCaptions] = useState<Record<string, string>>({});
  const [templateName, setTemplateName] = useState('');

  const refresh = async () => {
    setLoading(true);
    setError('');
    try {
      const conn = await (await apiFetch(base + '/connection')).json() as Connection;
      setConnection(conn);
      if (conn.connected) {
        const state = await (await apiFetch(base + '/state')).json() as PromotionState;
        setData(state);
      } else {
        setData(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Tidak dapat menyambung Promotion Center');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void refresh(); }, []);
  const run = async (description: string, task: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('');
    try {
      await task();
      setNotice(description);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Permintaan gagal');
    } finally {
      setBusy(false);
    }
  };
  const post = async (route: string, payload: object = {}) => {
    const response = await apiFetch(base + '/' + route, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    });
    return response.json();
  };
  const toggle = (value: string, set: React.Dispatch<React.SetStateAction<string[]>>) =>
    set(prev => prev.includes(value) ? prev.filter(id => id !== value) : [...prev, value]);
  const addDestination = async (event: React.FormEvent) => {
    event.preventDefault();
    await run('Destinasi telah disimpan.', async () => {
      await post('destination', {
        ...(editingId ? { id: editingId } : {}),
        name: destinationName.trim(), kind, target_url: destinationUrl.trim(),
        telegram_chat_id: kind === 'google_form' ? null : chatId.trim(),
        form_email: kind === 'google_form' ? gmail.trim() : null,
        form_message_entry: kind === 'google_form' ? formMessageEntry.trim() : null,
        form_email_entry: kind === 'google_form' ? formEmailEntry.trim() : null,
        form_fixed_fields: kind === 'google_form' ? editingFixedFields : {},
        submission_mode: kind === 'google_form' ? formMode : 'manual',
        auto_submit_authorized: kind === 'google_form' && formMode === 'auto' && formAuthorized,
        posting_permitted: permitted, active: editingId ? editingActive : true,
      });
      setDestinationName(''); setDestinationUrl(''); setChatId('');
      setGmail(''); setFormEmailEntry(''); setFormMessageEntry(''); setPermitted(false); setEditingId(null); setEditingActive(true); setEditingFixedFields({}); setFormMode('manual'); setFormAuthorized(false);
    });
  };
  const editDestination = (d: Destination) => {
    setEditingId(d.id); setKind(d.kind); setDestinationName(d.name); setDestinationUrl(d.target_url);
    setChatId(d.telegram_chat_id || ''); setGmail(d.form_email || '');
    setFormMessageEntry(d.form_message_entry || ''); setFormEmailEntry(d.form_email_entry || '');
    setPermitted(d.posting_permitted); setEditingActive(d.active); setEditingFixedFields(d.form_fixed_fields || {});
    setFormMode(d.submission_mode || 'manual'); setFormAuthorized(d.auto_submit_authorized === true); setTab('destinations');
    window.scrollTo({top: 0, behavior: 'smooth'});
  };
  const toggleActive = (d: Destination) => void run(
    d.active ? 'Destinasi telah dipause.' : 'Destinasi diaktifkan semula.',
    async () => { await post('destination', {...d, active: !d.active}); },
  );
  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selected.length && !accounts.length) { setError('Pilih sekurang-kurangnya satu destinasi.'); return; }
    const accountTooLong = accounts.some(id => (captions[id] || message).trim().length > 500);
    if (accountTooLong) { setError('Threads memerlukan mesej maksimum 500 aksara bagi setiap akaun.'); return; }
    const formManualCount = allDestinations.filter(d => selected.includes(d.id) && d.kind === 'google_form' &&
      !(d.submission_mode === 'auto' && d.auto_submit_authorized && data?.auto_form_submission)).length;
    if (!window.confirm('Hantar kempen ke ' + (selected.length + accounts.length) +
      ' destinasi? ' + formManualCount + ' Google Forms memerlukan submit manual. Semak mesej sebelum teruskan.')) return;
    await run('Kempen telah dimasukkan ke queue. Semak History untuk status sebenar.', async () => {
      await post('campaign', {
        title: title.trim(), message: message.trim(), destination_ids: selected,
        threads_account_ids: accounts,
        threads_captions: Object.fromEntries(Object.entries(captions).filter(([id, value]) => accounts.includes(id) && value.trim())),
        ...(schedule ? { scheduled_for: new Date(schedule).toISOString() } : {}),
      });
      setTitle(''); setMessage(''); setSchedule(''); setSelected([]); setAccounts([]); setCaptions({});
      setTab('history');
    });
  };
  const connectThreads = async () => {
    setBusy(true); setError('');
    try {
      const result = await post('threads/connect');
      if (result.url && typeof result.url === 'string' && result.url.startsWith('https://threads.net/')) {
        window.location.assign(result.url);
      } else { setError('Pautan sambungan Threads tidak sah.'); }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'OAuth Threads gagal');
    } finally { setBusy(false); }
  };
  const isReady = connection?.connected === true;
  const allDestinations = data?.destinations || [];
  const allAccounts = data?.threads_accounts || [];
  const selectAll = (automaticOnly: boolean) => {
    const allowed = allDestinations.filter(d => d.active && d.posting_permitted &&
      (!automaticOnly || d.kind !== 'google_form' ||
        (d.submission_mode === 'auto' && d.auto_submit_authorized && data?.auto_form_submission)));
    const enabledAccounts = allAccounts.filter(a => a.active && (!a.expires_at || new Date(a.expires_at).getTime() > Date.now()));
    setSelected(allowed.map(d => d.id)); setAccounts(enabledAccounts.map(a => a.id));
    setNotice(automaticOnly ? 'Destinasi automatik dipilih; Google Forms manual dikecualikan.' :
      'Semua destinasi yang dibenarkan dipilih. Google Forms manual masih perlukan submit.');
    setError('');
  };
  const campaigns = data?.campaigns || [];
  const deliveries = data?.deliveries || [];
  const tabs = [
    { id: 'campaign' as const, name: 'Kempen', icon: Send },
    { id: 'destinations' as const, name: 'Destinasi', icon: Link2 },
    { id: 'threads' as const, name: 'Threads', icon: MessageCircle },
    { id: 'history' as const, name: 'History', icon: ListChecks },
  ];

  return <div className="space-y-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div className="text-xs uppercase tracking-widest font-semibold text-pink-400">Berry Store / Marketing</div>
        <h1 className="mt-1 text-2xl font-bold text-white font-display">Promotion Center</h1>
        <p className="mt-1 text-sm text-slate-400">Satu tempat untuk Telegram group, channel, Google Forms dan sehingga 3 akaun Threads.</p>
      </div>
      <button type="button" className={secondary} onClick={() => void refresh()} disabled={busy || loading}>
        <RefreshCw className="mr-1.5 inline h-4 w-4" /> Refresh
      </button>
    </div>

    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {[
        ['Telegram', allDestinations.filter(d => d.kind !== 'google_form').length],
        ['Google Forms', allDestinations.filter(d => d.kind === 'google_form').length],
        ['Threads', allAccounts.length + '/3'],
        ['Campaigns', campaigns.length],
      ].map(([name, value]) => <div key={name} className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
        <div className="text-xs text-slate-400">{name}</div>
        <div className="mt-2 text-2xl font-semibold text-white">{value}</div>
      </div>)}
    </div>
    {!isReady && <div role="alert" className="rounded-xl border border-amber-800 bg-amber-950/40 p-4 text-sm text-amber-200">
      <AlertTriangle className="mr-2 inline h-4 w-4" />
      Sambungan Promotion Center belum aktif. Admin perlu konfigurasi bridge selamat pada Render. Tiada promosi akan dihantar selagi belum connected.
    </div>}
    {error && <div role="alert" className="rounded-xl border border-red-800 bg-red-950/40 p-3 text-sm text-red-200">{error}</div>}
    {notice && <div role="status" className="rounded-xl border border-emerald-800 bg-emerald-950/30 p-3 text-sm text-emerald-200"><CheckCircle2 className="mr-2 inline h-4 w-4" />{notice}</div>}
    <div className="flex gap-2 overflow-x-auto border-b border-slate-800 pb-3">
      {tabs.map(t => <button key={t.id} type="button" onClick={() => setTab(t.id)}
        aria-current={tab === t.id ? 'page' : undefined}
        className={tab === t.id ? 'flex shrink-0 items-center gap-2 rounded-xl bg-pink-600 px-4 py-2.5 text-sm font-semibold text-white' : 'flex shrink-0 items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm text-slate-300 hover:text-white'}>
        <t.icon className="h-4 w-4" />{t.name}
      </button>)}
    </div>

    {tab === 'campaign' && <div className="grid gap-5 lg:grid-cols-5">
      <form onSubmit={e => void send(e)} className={panel + ' lg:col-span-3'}>
        <div><h2 className="text-lg font-semibold text-white">Kempen baharu</h2><p className="text-xs text-slate-400">Tulis sekali, pilih destinasi dan send atau schedule.</p></div>
        <div><label htmlFor="pc-title" className={label}>Nama kempen</label><input id="pc-title" required maxLength={120} className={field} value={title} onChange={e => setTitle(e.target.value)} placeholder="Promosi November Berry Store" /></div>
        <div><label htmlFor="pc-template" className={label}>Template tersimpan (optional)</label>
          <select id="pc-template" className={field} defaultValue="" onChange={e => { const t = data?.templates.find(t => t.id === e.target.value); if (t) { setMessage(t.message); } }}>
            <option value="">Pilih template</option>{data?.templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </div>
        <div><label htmlFor="pc-message" className={label}>Mesej promosi</label>
          <textarea id="pc-message" className={field} required maxLength={1800} rows={6} value={message} onChange={e => setMessage(e.target.value)} placeholder="🍓 Berry Store — promo hari ini..." />
          <p className="mt-1 text-right text-[11px] text-slate-500">{message.length}/1800 karakter</p>
        </div>
        <div>
          <div className="mb-3 flex flex-wrap gap-2">
            <button type="button" className={secondary} onClick={() => selectAll(true)}>Pilih Semua Auto</button>
            <button type="button" className={secondary} onClick={() => selectAll(false)}>Pilih Semua Termasuk Manual</button>
            <button type="button" className={secondary} onClick={() => { setSelected([]); setAccounts([]); }}>Kosongkan Pilihan</button>
          </div>
          <div className={label}>Destinasi Telegram & Google Forms</div>
          <div className="max-h-44 space-y-2 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-3">
            {!allDestinations.length && <p className="text-xs text-slate-500">Belum ada destinasi. Tambah melalui tab Destinasi.</p>}
            {allDestinations.map(d => <label key={d.id} className="flex cursor-pointer items-center gap-3 text-sm text-slate-200">
              <input type="checkbox" checked={selected.includes(d.id)} disabled={!d.active || !d.posting_permitted}
                onChange={() => toggle(d.id, setSelected)} className="accent-pink-500" />
              <span className="flex-1 truncate">{d.name}</span>
              <span className="text-[10px] text-slate-400">{d.kind === 'google_form' ? (d.submission_mode === 'auto' && d.auto_submit_authorized && data?.auto_form_submission ? 'Form · auto' : 'Form · manual') : d.kind.replace('telegram_', '')}</span>
            </label>)}
          </div>
        </div>
        <div>
          <div className={label}>Akaun Threads</div>
          <div className="space-y-2">
            {!allAccounts.length && <p className="text-xs text-slate-500">Belum connect akaun Threads.</p>}
            {allAccounts.map(a => <div key={a.id} className="rounded-xl border border-slate-800 bg-slate-950 p-3">
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={accounts.includes(a.id)} onChange={() => toggle(a.id, setAccounts)} className="accent-pink-500" />@{a.username}</label>
              {accounts.includes(a.id) && <textarea rows={2} maxLength={500} value={captions[a.id] || ''} onChange={e => setCaptions(prev => ({...prev, [a.id]: e.target.value}))} className={field + ' mt-2'} placeholder="Custom caption akaun ini (optional, max 500). Jika kosong guna mesej utama." />}
            </div>)}
          </div>
        </div>
        <div><label htmlFor="pc-schedule" className={label}>Schedule (optional) <CalendarDays className="ml-1 inline h-3.5 w-3.5"/></label>
          <input id="pc-schedule" type="datetime-local" className={field} value={schedule} onChange={e => setSchedule(e.target.value)} />
          <p className="mt-1 text-[11px] text-slate-500">Kosong = hantar sekarang. Masa mengikut timezone browser. Jadual maksimum 60 hari.</p>
        </div>
        <p className="text-xs text-slate-400">{selected.length + accounts.length} destinasi dipilih ·
          {allDestinations.filter(d => selected.includes(d.id) && d.kind === 'google_form' &&
          !(d.submission_mode === 'auto' && d.auto_submit_authorized && data?.auto_form_submission)).length} perlu submit manual</p>
        <button className={primary} disabled={!isReady || busy || !title.trim() || !message.trim() || (!selected.length && !accounts.length) || accounts.some(id => (captions[id] || message).trim().length > 500)} type="submit"><Send className="mr-2 inline h-4 w-4"/>{schedule ? 'Jadualkan Kempen' : 'Confirm & Send'}</button>
        <p className="text-xs text-slate-400">Satu kempen boleh menghantar ke Telegram dan Threads yang sudah connected. Google Forms Auto hanya untuk form yang mengizinkan automasi; form lain menghasilkan prefilled link untuk submit manual. Semak confirmation setiap destinasi dalam History.</p>
      </form>
      <div className="space-y-5 lg:col-span-2">
        <section className={panel}>
          <h2 className="text-sm font-semibold text-white">Pratonton mesej</h2>
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <div className="text-xs font-semibold text-pink-400">Berry Store</div>
            <p className="mt-3 whitespace-pre-wrap break-words text-sm text-slate-200">{message || 'Mesej promosi akan dipaparkan di sini.'}</p>
          </div>
          <p className="text-xs text-slate-400">Threads mempunyai had 500 karakter setiap post. Jika mesej lebih panjang, isi custom caption untuk setiap akaun.</p>
        </section>
        <section className={panel}>
          <h2 className="text-sm font-semibold text-white">Simpan template</h2>
          <input className={field} value={templateName} onChange={e => setTemplateName(e.target.value)} maxLength={120} placeholder="Nama template" aria-label="Nama template" />
          <button type="button" className={secondary} disabled={!isReady || busy || !templateName.trim() || !message.trim()} onClick={() => void run('Template disimpan.', async () => { await post('template', {name: templateName.trim(), message: message.trim()}); setTemplateName(''); })}>Simpan mesej sebagai template</button>
        </section>
      </div>
    </div>}

    {tab === 'destinations' && <div className="grid gap-5 lg:grid-cols-5">
      <form onSubmit={e => void addDestination(e)} className={panel + ' lg:col-span-2'}>
        <h2 className="text-lg font-semibold text-white"><Plus className="mr-2 inline h-4 w-4"/>{editingId ? 'Edit destinasi' : 'Tambah destinasi'}</h2>
        <div><label className={label} htmlFor="pc-kind">Jenis</label>
          <select id="pc-kind" className={field} value={kind} onChange={e => setKind(e.target.value as Destination['kind'])}>
            <option value="telegram_group">Telegram Group</option><option value="telegram_channel">Telegram Channel</option><option value="google_form">Google Form Confession</option>
          </select>
        </div>
        <div><label className={label} htmlFor="pc-dname">Nama</label><input id="pc-dname" className={field} required maxLength={120} value={destinationName} onChange={e => setDestinationName(e.target.value)} placeholder="Group IPTA / Confession Kampus" /></div>
        <div><label className={label} htmlFor="pc-durl">Link {kind === 'google_form' ? 'Google Form' : 'Telegram'}</label><input id="pc-durl" required type="url" className={field} value={destinationUrl} onChange={e => setDestinationUrl(e.target.value)} placeholder={kind === 'google_form' ? 'https://docs.google.com/forms/d/e/.../viewform' : 'https://t.me/namagroup'} /></div>
        {kind !== 'google_form' ? <div><label className={label} htmlFor="pc-chat">Chat ID / @username</label><input id="pc-chat" required className={field} value={chatId} onChange={e => setChatId(e.target.value)} placeholder="-100... atau @channel" /><p className="mt-1 text-[11px] text-slate-500">Bot mesti ada akses dan permission untuk post. Link sahaja tidak cukup.</p></div> :
          <>
            <div><label className={label} htmlFor="pc-gmail">Gmail untuk isi form (bukan password)</label><input id="pc-gmail" className={field} type="email" value={gmail} onChange={e => setGmail(e.target.value)} placeholder="email@gmail.com"/></div>
            <div><label className={label} htmlFor="pc-msgentry">Message field ID</label><input id="pc-msgentry" className={field} value={formMessageEntry} onChange={e => setFormMessageEntry(e.target.value)} placeholder="entry.123456789"/></div>
            <div><label className={label} htmlFor="pc-emailentry">Email field ID</label><input id="pc-emailentry" className={field} value={formEmailEntry} onChange={e => setFormEmailEntry(e.target.value)} placeholder="entry.987654321"/></div>
            <div>
              <label htmlFor="pc-form-mode" className={label}>Kaedah penghantaran Google Forms</label>
              <select id="pc-form-mode" className={field} value={formMode} onChange={e => setFormMode(e.target.value as 'manual'|'auto')}>
                <option value="manual">Manual — prefilled link</option>
                <option value="auto">Auto-submit — hanya dengan kebenaran pemilik form</option>
              </select>
              {formMode === 'auto' && <>
                <label className="mt-3 flex gap-2 rounded-xl border border-amber-800 bg-amber-950/20 p-3 text-xs text-amber-100">
                  <input className="mt-0.5 accent-pink-500" type="checkbox" checked={formAuthorized} onChange={e => setFormAuthorized(e.target.checked)}/>
                  Saya mendapat kebenaran jelas daripada pemilik Google Form untuk menghantar respons promosi secara automatik.
                </label>
                <p className="mt-2 text-xs text-amber-300">Auto-submit hanya untuk form awam yang menerima respons, tanpa CAPTCHA/login, dan dihadkan sekali setiap form dalam 24 jam. Status Sent hanya selepas Google memulangkan confirmation. Jika tidak pasti, perlu semakan manual.</p>
                {!data?.auto_form_submission && <p className="mt-2 text-xs text-amber-300">Auto-submit Google Form belum diaktifkan di backend. Sehingga aktif, ia akan kekal manual.</p>}
              </>}
            </div>
          </>}
        <label className="flex items-start gap-3 rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300">
          <input type="checkbox" checked={permitted} onChange={e => setPermitted(e.target.checked)} className="mt-0.5 accent-pink-500" />
          Saya telah semak peraturan destinasi dan dibenarkan menghantar promosi.
        </label>
        <div className="flex flex-wrap gap-2"><button className={primary} type="submit" disabled={!isReady || busy || !permitted || (kind === 'google_form' && formMode === 'auto' && (!formAuthorized || !formMessageEntry.trim()))}>{editingId ? 'Simpan Perubahan' : 'Simpan Destinasi'}</button>
        {editingId && <button type="button" className={secondary} onClick={() => { setEditingId(null); setDestinationName(''); setDestinationUrl(''); setChatId(''); setGmail(''); setFormMessageEntry(''); setFormEmailEntry(''); setPermitted(false); setFormMode('manual'); setFormAuthorized(false); }}>Batal Edit</button>}</div>
      </form>
      <div className={panel + ' lg:col-span-3'}>
        <h2 className="text-lg font-semibold text-white">Semua destinasi ({allDestinations.length})</h2>
        {!allDestinations.length && <p className="text-sm text-slate-400">Belum ada destinasi. Masukkan group, channel atau Google Form di sebelah.</p>}
        {allDestinations.map(d => <div key={d.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-950 p-3">
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-white">{d.name}</div>
            <div className="break-all text-xs text-slate-400">{d.target_url}</div>
            <div className="text-[11px] text-pink-400">{d.kind.replace('_', ' ')} · {d.active ? 'Active' : 'Paused'} · {d.kind === 'google_form' ? (d.submission_mode === 'auto' && d.auto_submit_authorized ? 'Auto-submit opt-in' : 'Manual') : (d.posting_permitted ? 'posting permitted' : 'belum dibenarkan')}</div>
          </div>
          <a href={d.target_url} target="_blank" rel="noreferrer" className={secondary}>Buka <ExternalLink className="inline h-3 w-3"/></a>
          <button type="button" className={secondary} disabled={busy || !isReady} onClick={() => editDestination(d)}>Edit</button>
          <button type="button" className={secondary} disabled={busy || !isReady} onClick={() => toggleActive(d)}>{d.active ? 'Pause' : 'Resume'}</button>
          {d.kind !== 'google_form' && <button type="button" disabled={busy || !isReady} className={secondary} onClick={() => void run('Sambungan Telegram disemak.', async () => { const result = await post('destination/' + d.id + '/test'); setNotice(result.message || 'Bot boleh melihat destinasi.'); })}>Test Connection</button>}
        </div>)}
      </div>
    </div>}

    {tab === 'threads' && <div className={panel}>
      <h2 className="text-lg font-semibold text-white">Connect sehingga 3 akaun Threads</h2>
      <p className="text-sm text-slate-400">Setiap akaun perlu memberi kebenaran melalui Meta OAuth. Tiada password Threads disimpan dalam dashboard.</p>
      <button type="button" className={primary} disabled={!isReady || busy || !data?.threads_configured || allAccounts.length >= 3} onClick={() => void connectThreads()}><Plus className="mr-1.5 inline h-4 w-4"/>Connect Threads Account</button>
      {isReady && !data?.threads_configured && <p className="text-xs text-amber-300">Meta Threads App ID/Secret dan token encryption key belum lengkap pada server production.</p>}
      {!allAccounts.length && <p className="text-sm text-slate-400">Belum ada akaun Threads yang disambungkan.</p>}
      {allAccounts.map(a => <div key={a.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-950 p-3">
        <div className="flex-1"><div className="text-sm font-semibold text-white">@{a.username}</div><p className="text-xs text-slate-400">Token expiry: {date(a.expires_at)}</p></div>
        <button type="button" className={secondary} disabled={busy || !isReady} onClick={() => void run('Threads account disconnected.', async () => { await post('threads/' + a.id + '/disconnect'); })}>Disconnect</button>
      </div>)}
      <p className="text-xs text-slate-400">Sokongan semasa: text posts sahaja, maksimum 500 karakter setiap akaun. Media & analytics belum tersedia.</p>
    </div>}

    {tab === 'history' && <div className={panel}>
      <h2 className="text-lg font-semibold text-white">Sejarah kempen & delivery report</h2>
      {!campaigns.length && <p className="text-sm text-slate-400">Belum ada kempen direkodkan.</p>}
      {campaigns.map(c => <div key={c.id} className="space-y-3 rounded-xl border border-slate-800 bg-slate-950 p-4">
        <div className="flex flex-wrap justify-between gap-3"><div><div className="text-sm font-semibold text-white">{c.title}</div><div className="text-xs text-slate-400">{date(c.scheduled_for)}</div></div><span className="h-fit rounded-full bg-slate-800 px-3 py-1 text-xs font-semibold text-pink-300">{c.state === 'completed' ? 'Processing complete' : c.state}</span></div>
        <div className="flex flex-wrap gap-2 text-xs">
          {(() => { const list = deliveries.filter(d => d.campaign_id === c.id);
            const sent = list.filter(d => d.state === 'sent').length;
            const manual = list.filter(d => d.state === 'manual').length;
            const failed = list.filter(d => ['failed','unknown','skipped'].includes(d.state)).length;
            return <><span className="rounded-full bg-emerald-950/50 px-3 py-1 text-emerald-300">{sent} Submitted / Sent</span>
              <span className="rounded-full bg-amber-950/50 px-3 py-1 text-amber-300">{manual} Manual Required</span>
              <span className="rounded-full bg-red-950/50 px-3 py-1 text-red-300">{failed} Failed / Unconfirmed</span></>;
          })()}
        </div>
        <p className="line-clamp-3 whitespace-pre-wrap text-xs text-slate-300">{c.message}</p>
        <div className="space-y-2">
          {deliveries.filter(d => d.campaign_id === c.id).map(d => {
            const dest = allDestinations.find(x => x.id === d.destination_id);
            const account = allAccounts.find(x => x.id === d.threads_account_id);
            return <div key={d.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-800 p-2 text-xs">
              <div><span className="font-semibold text-slate-200">{dest?.name || (account ? '@' + account.username : 'Destinasi')}</span><span className="ml-2 text-pink-300">{d.state === 'sent' ? (dest?.kind === 'google_form' ? 'Submitted' : 'Sent') :
              d.state === 'manual' ? 'Manual Required' : d.state === 'unknown' ? 'Unconfirmed' :
              d.state === 'failed' ? 'Failed' : d.state}</span>{d.error_message && <div className="text-amber-300">{d.error_message}</div>}</div>
              {d.state === 'manual' && d.external_id?.startsWith('https://') && <a href={d.external_id} target="_blank" rel="noreferrer" className="text-pink-400 underline">Buka form untuk submit <ExternalLink className="inline h-3 w-3"/></a>}
            </div>;
          })}
        </div>
        <div className="flex flex-wrap gap-2">
          {c.state === 'queued' && <button type="button" disabled={busy || !isReady} className={secondary} onClick={() => void run('Kempen dibatalkan.', async () => { await post('campaign/' + c.id + '/cancel'); })}>Cancel Campaign</button>}
          {c.state === 'completed' && deliveries.some(d => d.campaign_id === c.id && d.state === 'failed') && <button type="button" disabled={busy || !isReady} className={secondary} onClick={() => void run('Delivery gagal dimasukkan semula ke queue.', async () => { await post('campaign/' + c.id + '/retry'); })}>Retry Failed Only</button>}
        </div>
      </div>)}
    </div>}
  </div>;
}
