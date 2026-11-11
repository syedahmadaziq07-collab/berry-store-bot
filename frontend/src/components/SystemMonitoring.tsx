import React from 'react';
import {
  Activity,
  Server,
  Database,
  Bot,
  Zap,
  ShieldCheck,
  CheckCircle2,
  Clock,
  Terminal,
} from 'lucide-react';
import { AuditLog } from '../types/store';

interface SystemMonitoringProps {
  auditLogs: AuditLog[];
  health: any;
  onRefreshHealth: () => void;
}

export const SystemMonitoring: React.FC<SystemMonitoringProps> = ({
  auditLogs,
  health,
  onRefreshHealth,
}) => {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold text-white font-display">Pemantauan Sistem & Log Audit</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Status penyambungan pelayan Render, pangkalan data Supabase, Telegram API & jejak audit aktiviti pemilik
          </p>
        </div>

        <button
          type="button"
          onClick={onRefreshHealth}
          className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-xl flex items-center gap-1.5 transition-colors cursor-pointer self-start sm:self-auto border border-slate-700"
        >
          <Activity className="w-3.5 h-3.5 text-pink-400" />
          <span>Segarkan Status API</span>
        </button>
      </div>

      {/* Service Health Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Telegram Bot */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg">
          <div className="flex items-center justify-between text-xs mb-2">
            <span className="text-slate-400">Telegram Bot Polling</span>
            <span className="w-2.5 h-2.5 rounded-full bg-slate-500 animate-pulse" />
          </div>
          <div className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-pink-400" />
            <span className="font-bold text-white text-sm">{health?.telegram || 'Belum diuji'}</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-2 font-mono">
            Polling tidak dijalankan oleh dashboard
          </div>
        </div>

        {/* Supabase Database */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg">
          <div className="flex items-center justify-between text-xs mb-2">
            <span className="text-slate-400">Supabase PostgreSQL</span>
            <span className="w-2.5 h-2.5 rounded-full bg-slate-500" />
          </div>
          <div className="flex items-center gap-2">
            <Database className="w-5 h-5 text-emerald-400" />
            <span className="font-bold text-white text-sm">{health?.database || 'Belum diuji'}</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-2 font-mono truncate">
            Status daripada ujian API server
          </div>
        </div>

        {/* Render Deployment */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg">
          <div className="flex items-center justify-between text-xs mb-2">
            <span className="text-slate-400">Render Hosting</span>
            <span className="w-2.5 h-2.5 rounded-full bg-slate-500" />
          </div>
          <div className="flex items-center gap-2">
            <Server className="w-5 h-5 text-purple-400" />
            <span className="font-bold text-white text-sm">{health?.mode || 'staging'}</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-2 font-mono">
            Host dashboard berasingan
          </div>
        </div>

        {/* AI Providers */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg">
          <div className="flex items-center justify-between text-xs mb-2">
            <span className="text-slate-400">fal.ai & ElevenLabs</span>
            <span className="w-2.5 h-2.5 rounded-full bg-slate-500" />
          </div>
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-400" />
            <span className="font-bold text-white text-sm">{health?.ai || 'Belum diuji'}</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-2 font-mono">
            Latency belum diukur
          </div>
        </div>
      </div>

      {/* Audit Logs Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-pink-400" />
            <h3 className="text-sm font-semibold text-white">Log Audit Tindakan Pemilik (Security Audit Trail)</h3>
          </div>
          <span className="text-xs text-slate-400 font-mono">
            {auditLogs.length} rekod audit disimpan
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 text-slate-400 uppercase font-mono tracking-wider border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">Masa & IP</th>
                <th className="px-4 py-3">Pelaku</th>
                <th className="px-4 py-3">Tindakan</th>
                <th className="px-4 py-3">Butiran Perubahan</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-200">
              {auditLogs.map(log => (
                <tr key={log.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-3 font-mono text-slate-400">
                    <div className="text-slate-300">
                      {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </div>
                    <div className="text-[10px] text-slate-400">{log.ip}</div>
                  </td>
                  <td className="px-4 py-3 font-semibold text-white">
                    {log.actor}
                  </td>
                  <td className="px-4 py-3">
                    <span className="bg-slate-950 px-2 py-0.5 rounded text-[10px] font-mono font-bold text-pink-400 border border-slate-800">
                      {log.action}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {log.details}
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
