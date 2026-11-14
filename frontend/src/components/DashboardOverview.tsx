import React, { useState } from 'react';
import {
  TrendingUp,
  Package,
  AlertTriangle,
  Clock,
  Sparkles,
  Wallet,
  ArrowUpRight,
  ShoppingBag,
  FileText,
  ExternalLink,
  ChevronRight,
} from 'lucide-react';
import { formatMYR } from '../utils/store-logic';
import { Order, Product } from '../types/store';

interface DashboardOverviewProps {
  kpis: any;
  orders: Order[];
  products: Product[];
  lowStockAlerts: any[];
  revenueTrend: any[];
  categoryRevenue: Record<string, number>;
  onNavigateToOrders: () => void;
  onNavigateToShop: () => void;
  onNavigateToAIStudio: () => void;
  onNavigateToTurnitin: () => void;
  onApproveOrder: (id: string) => void;
}

export const DashboardOverview: React.FC<DashboardOverviewProps> = ({
  kpis,
  orders,
  products,
  lowStockAlerts,
  revenueTrend,
  categoryRevenue,
  onNavigateToOrders,
  onNavigateToShop,
  onNavigateToAIStudio,
  onNavigateToTurnitin,
  onApproveOrder,
}) => {
  const [dateFilter, setDateFilter] = useState<'today' | 'yesterday' | '7d' | '30d'>('7d');

  const selectedTrend = dateFilter === 'today' ? revenueTrend.slice(-1) : dateFilter === 'yesterday' ? revenueTrend.slice(-2, -1) : dateFilter === '7d' ? revenueTrend.slice(-7) : revenueTrend;
  const pendingOrders = orders.filter(o => o.status === 'waiting_payment' || o.status === 'pending');

  return (
    <div className="space-y-6">
      {/* Date Filter & Overview Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-white font-display">Ringkasan Perniagaan (Store Overview)</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Analisis jualan masa nyata, pesanan pending & kawalan inventori Telegram bot
          </p>
        </div>

        {/* Date Filter Buttons */}
        <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 p-1 rounded-xl">
          <button
            type="button"
            onClick={() => setDateFilter('today')}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${
              dateFilter === 'today' ? 'bg-pink-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Today
          </button>
          <button
            type="button"
            onClick={() => setDateFilter('yesterday')}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${
              dateFilter === 'yesterday' ? 'bg-pink-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Yesterday
          </button>
          <button
            type="button"
            onClick={() => setDateFilter('7d')}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${
              dateFilter === '7d' ? 'bg-pink-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Last 7 Days
          </button>
          <button
            type="button"
            onClick={() => setDateFilter('30d')}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors cursor-pointer ${
              dateFilter === '30d' ? 'bg-pink-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Last 30 Days
          </button>
        </div>
      </div>

      {/* Match each Telegram home menu with its own admin module. */}
      <section aria-label="Kawalan kategori Telegram" className="grid gap-3 md:grid-cols-3">
        {[
          { label: 'Browse Shop', hint: 'Produk, harga, description & stock', icon: ShoppingBag, open: onNavigateToShop },
          { label: 'AI Studio', hint: 'AI Video, model, kredit & availability', icon: Sparkles, open: onNavigateToAIStudio },
          { label: 'Turnitin', hint: 'Similarity, AI Check, stock & report', icon: FileText, open: onNavigateToTurnitin },
        ].map(item => {
          const Icon = item.icon;
          return <div key={item.label} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-white"><Icon className="h-4 w-4 text-pink-400" />{item.label}</div>
            <p className="mt-2 text-xs text-slate-400">{item.hint}</p>
            <button type="button" onClick={item.open}
              className="mt-4 w-full rounded-lg bg-pink-600 px-3 py-2 text-xs font-semibold text-white hover:bg-pink-500">
              Urus {item.label} <ChevronRight className="ml-1 inline h-3 w-3" />
            </button>
          </div>;
        })}
      </section>

      {/* Urgent Action Alert Strip */}
      {(lowStockAlerts.length > 0 || pendingOrders.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Pending Payment Verification Alert */}
          {pendingOrders.length > 0 && (
            <div className="bg-pink-950/30 border border-pink-800/40 rounded-xl p-4 flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-pink-500/20 text-pink-400 rounded-lg shrink-0 mt-0.5">
                  <Clock className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-white">
                    {`${pendingOrders.length} Pesanan Menunggu Pengesahan Pembayaran`}
                  </h4>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Semak status dan bukti pembayaran sebelum meluluskan pesanan.
                  </p>
                  <div className="mt-2 text-xs font-medium text-pink-400">
                    Jumlah: {formatMYR(pendingOrders.reduce((sum, o) => sum + o.amount, 0))}
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={onNavigateToOrders}
                className="px-3 py-1.5 bg-pink-600 hover:bg-pink-500 text-white text-xs font-medium rounded-lg shrink-0 transition-colors cursor-pointer flex items-center gap-1"
              >
                <span>Semak</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* Low Stock Restock Alert */}
          {lowStockAlerts.length > 0 && (
            <div className="bg-amber-950/30 border border-amber-800/40 rounded-xl p-4 flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-amber-500/20 text-amber-400 rounded-lg shrink-0 mt-0.5">
                  <AlertTriangle className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-white">
                    Amaran Stok Rendah: {lowStockAlerts.length} Produk Kritikal
                  </h4>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {lowStockAlerts.map(p => `${p.name} (${p.stock} baki)`).join(', ')}
                  </p>
                  <p className="text-xs text-amber-400 mt-1">
                    Tambah kredensial atau laras stok untuk elak kehabisan di Telegram.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={onNavigateToShop}
                className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium rounded-lg shrink-0 transition-colors cursor-pointer flex items-center gap-1"
              >
                <span>Urus Stok</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Primary KPI Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Total Revenue */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>Total Revenue (MYR)</span>
            <div className="p-1.5 bg-emerald-500/10 text-emerald-400 rounded-md">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-white mt-2 font-mono tabular-nums">
            {formatMYR(kpis.totalRevenue || 0)}
          </div>
          <div className="flex items-center gap-1 text-xs text-emerald-400 mt-1 font-medium">
            <ArrowUpRight className="w-3.5 h-3.5" />
            <span>Hari ini: {formatMYR(kpis.revenueToday || 0)}</span>
          </div>
        </div>

        {/* Total Orders */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>Total Orders</span>
            <div className="p-1.5 bg-pink-500/10 text-pink-400 rounded-md">
              <Package className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-white mt-2 font-mono tabular-nums">
            {kpis.totalOrders || 0}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            <span className="text-emerald-400 font-medium">{kpis.completedOrdersCount} Selesai</span>
            {' · '}
            <span className="text-pink-400 font-medium">{kpis.pendingOrdersCount} Pending</span>
          </div>
        </div>

        {/* Jumlah Produk & Stock */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>Jumlah Produk</span>
            <div className="p-1.5 bg-indigo-500/10 text-indigo-400 rounded-md">
              <ShoppingBag className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-white mt-2 font-mono tabular-nums">
            {kpis.totalProducts || 0}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {kpis.lowStockCount > 0 ? (
              <span className="text-amber-400 font-medium">{kpis.lowStockCount} amaran stok rendah</span>
            ) : (
              <span className="text-emerald-400 font-medium">Stok mencukupi</span>
            )}
          </div>
        </div>

        {/* AI Studio Wallet Liabilities */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>AI Wallet Liability</span>
            <div className="p-1.5 bg-purple-500/10 text-purple-400 rounded-md">
              <Wallet className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-white mt-2 font-mono tabular-nums">
            {formatMYR(kpis.aiWalletLiability || 0)}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            <span>Untung Kasar Anggaran: </span>
            <span className="text-emerald-400 font-semibold">{kpis.estimatedGrossProfit == null ? 'Belum tersedia' : formatMYR(kpis.estimatedGrossProfit)}</span>
          </div>
        </div>
      </div>

      {/* Analytics: 7-Day Revenue Trend & Category Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Revenue Trend Visualizer */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-semibold text-white">Trend Jualan (Revenue Trend)</h3>
              <p className="text-xs text-slate-400">Prestasi hasil jualan harian di Telegram Store (RM)</p>
            </div>
            <span className="text-xs font-mono text-pink-400 bg-pink-500/10 px-2.5 py-1 rounded-md border border-pink-500/20">
              Avg: {formatMYR(selectedTrend.length ? selectedTrend.reduce((sum, d) => sum + d.revenue, 0) / selectedTrend.length : 0)}/hari
            </span>
          </div>

          {/* Bar Chart Simulation */}
          <div className="h-48 flex items-end justify-between gap-2 pt-6 pb-2 px-2 border-b border-slate-800">
            {selectedTrend.map((day: any) => {
              const maxVal = Math.max(1, ...selectedTrend.map(d => d.revenue));
              const heightPct = Math.min(100, Math.round((day.revenue / maxVal) * 100));
              return (
                <div key={day.date} className="flex-1 flex flex-col items-center gap-2 group relative">
                  {/* Tooltip */}
                  <div className="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-10 bg-slate-800 text-white text-[11px] font-mono px-2 py-1 rounded shadow-lg pointer-events-none whitespace-nowrap z-10 border border-slate-700">
                    {formatMYR(day.revenue)}
                  </div>
                  <div className="w-full bg-slate-800/80 rounded-t-md relative flex items-end h-36 overflow-hidden">
                    <div
                      style={{ height: `${heightPct}%` }}
                      className="w-full bg-gradient-to-t from-pink-600 to-purple-500 rounded-t-md transition-all duration-500 group-hover:from-pink-500 group-hover:to-purple-400"
                    />
                  </div>
                  <span className="text-[11px] font-mono text-slate-400 text-center">
                    {day.date.slice(5)}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="flex items-center justify-between text-xs text-slate-400 mt-3 pt-1">
            <span>Minggu ini: <strong className="text-slate-200">{formatMYR(kpis.revenueThisWeek || 0)}</strong></span>
            <span>Bulan ini: <strong className="text-slate-200">{formatMYR(kpis.revenueThisMonth || 0)}</strong></span>
          </div>
        </div>

        {/* Category Share & Best Selling Services */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white mb-1">Pecahan Kategori Jualan</h3>
            <p className="text-xs text-slate-400 mb-4">Sumbangan hasil mengikut kategori produk</p>

            <div className="space-y-3">
              {Object.keys(categoryRevenue).length === 0 && <p className="text-xs text-slate-400">Pemetaan kategori belum tersedia dalam database.</p>}
              {Object.entries(categoryRevenue).map(([cat, amount]) => {
                const total = kpis.totalRevenue || 1;
                const pct = Math.round((amount / total) * 100);
                return (
                  <div key={cat}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="font-medium text-slate-300">{cat}</span>
                      <span className="font-mono text-slate-400">{formatMYR(amount)} ({pct}%)</span>
                    </div>
                    <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        style={{ width: `${pct}%` }}
                        className="h-full bg-gradient-to-r from-pink-500 to-purple-500 rounded-full"
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-slate-800/80">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>Penggunaan Berry AI Studio</span>
              <span className="font-mono text-purple-400 font-semibold">{kpis.aiJobsGenerated == null ? 'Belum tersedia' : `${kpis.aiJobsGenerated} tugasan dibuat`}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Orders Quick Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white">Pesanan Terkini (Recent Orders)</h3>
            <p className="text-xs text-slate-400">Status kelulusan pembayaran dan penghantaran kredensial</p>
          </div>
          <button
            type="button"
            onClick={onNavigateToOrders}
            className="text-xs text-pink-400 hover:text-pink-300 flex items-center gap-1 font-medium cursor-pointer"
          >
            <span>Lihat Semua Pesanan</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 text-slate-400 uppercase font-mono tracking-wider border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">Order ID</th>
                <th className="px-4 py-3">Pelanggan</th>
                <th className="px-4 py-3">Produk</th>
                <th className="px-4 py-3 text-right">Amaun (RM)</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Tindakan</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-200">
              {orders.slice(0, 5).map(order => (
                <tr key={order.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-3 font-mono text-slate-300 font-semibold">
                    {order.id}
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-white">{order.customer_name || `@${order.username}`}</div>
                    <div className="text-[11px] text-slate-400 font-mono">ID: {order.user_id}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {order.product_name}
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-semibold text-white tabular-nums">
                    {formatMYR(order.amount)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block px-2.5 py-0.5 rounded-md text-[11px] font-medium font-mono ${
                        order.status === 'completed'
                          ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                          : order.status === 'waiting_payment'
                          ? 'bg-pink-500/15 text-pink-300 border border-pink-500/30'
                          : order.status === 'rejected'
                          ? 'bg-red-500/15 text-red-300 border border-red-500/30'
                          : 'bg-slate-800 text-slate-300'
                      }`}
                    >
                      {order.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {order.status === 'waiting_payment' ? (
                      <button
                        type="button"
                        onClick={() => onApproveOrder(order.id)}
                        className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-medium transition-colors cursor-pointer"
                      >
                        Lulus Bayaran
                      </button>
                    ) : (
                      <span className="text-slate-400 text-xs">Selesai</span>
                    )}
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
