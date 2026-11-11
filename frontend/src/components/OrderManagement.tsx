import React, { useState } from 'react';
import {
  Search,
  CheckCircle2,
  XCircle,
  Eye,
  Clock,
  Download,
  AlertCircle,
  X,
  ShieldCheck,
  Receipt,
  User,
} from 'lucide-react';
import { Order } from '../types/store';
import { formatMYR, canTransitionOrderStatus } from '../utils/store-logic';

interface OrderManagementProps {
  orders: Order[];
  onUpdateOrderStatus: (orderId: string, status: Order['status'], reason?: string) => Promise<void>;
}

export const OrderManagement: React.FC<OrderManagementProps> = ({
  orders,
  onUpdateOrderStatus,
}) => {
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedReceiptOrder, setSelectedReceiptOrder] = useState<Order | null>(null);
  const [rejectingOrder, setRejectingOrder] = useState<Order | null>(null);
  const [rejectReason, setRejectReason] = useState('Resit bayaran tidak sah atau jumlah tidak sepadan');
  const [processingId, setProcessingId] = useState<string | null>(null);

  const filteredOrders = orders.filter(o => {
    if (statusFilter !== 'all' && o.status !== statusFilter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        o.id.toLowerCase().includes(q) ||
        o.username.toLowerCase().includes(q) ||
        o.product_name.toLowerCase().includes(q) ||
        String(o.user_id).includes(q)
      );
    }
    return true;
  });

  const handleApprove = async (order: Order) => {
    const check = canTransitionOrderStatus(order.status, 'completed');
    if (!check.allowed) {
      return;
    }

    setProcessingId(order.id);
    try {
      await onUpdateOrderStatus(order.id, 'completed');
    } finally {
      setProcessingId(null);
    }
  };

  const handleRejectSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectingOrder) return;
    setProcessingId(rejectingOrder.id);
    try {
      await onUpdateOrderStatus(rejectingOrder.id, 'rejected', rejectReason);
      setRejectingOrder(null);
    } finally {
      setProcessingId(null);
    }
  };

  const handleExportCSV = () => {
    const headers = ['Order ID', 'Telegram User ID', 'Username', 'Product', 'Amount RM', 'Status', 'Date', 'Notes'];
    const rows = filteredOrders.map(o => [
      o.id,
      o.user_id,
      o.username,
      `"${o.product_name.replace(/"/g, '""')}"`,
      o.amount.toFixed(2),
      o.status,
      o.created_at,
      `"${(o.notes || '').replace(/"/g, '""')}"`,
    ]);

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `berry_store_orders_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold text-white font-display">Pengurusan Pesanan & Resit Bayaran</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Semak pembayaran DuitNow/bank, luluskan pesanan & hantar kredensial langganan
          </p>
        </div>

        <button
          type="button"
          onClick={handleExportCSV}
          className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-xl flex items-center gap-1.5 transition-colors cursor-pointer self-start sm:self-auto border border-slate-700"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Eksport CSV</span>
        </button>
      </div>

      {/* Filter Tabs & Search Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Status Filters */}
        <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 p-1 rounded-xl overflow-x-auto text-xs">
          {[
            { id: 'all', label: 'Semua' },
            { id: 'waiting_payment', label: 'Menunggu Semakan' },
            { id: 'completed', label: 'Selesai' },
            { id: 'rejected', label: 'Ditolak' },
          ].map(tab => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setStatusFilter(tab.id)}
              className={`px-3 py-1.5 font-medium rounded-lg transition-colors shrink-0 cursor-pointer ${
                statusFilter === tab.id
                  ? 'bg-pink-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {tab.label} ({tab.id === 'all' ? orders.length : orders.filter(o => o.status === tab.id).length})
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative w-full md:w-72">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Cari order ID, username, produk..."
            className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-pink-500"
          />
        </div>
      </div>

      {/* Orders Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 text-slate-400 uppercase font-mono tracking-wider border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">Order ID & Masa</th>
                <th className="px-4 py-3">Pelanggan Telegram</th>
                <th className="px-4 py-3">Item Langganan</th>
                <th className="px-4 py-3 text-right">Amaun (RM)</th>
                <th className="px-4 py-3 text-center">Resit Bayaran</th>
                <th className="px-4 py-3 text-center">Status</th>
                <th className="px-4 py-3 text-right">Tindakan Kelulusan</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-200">
              {filteredOrders.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-400">
                    Tiada pesanan dijumpai mengikut tapisan ini.
                  </td>
                </tr>
              ) : (
                filteredOrders.map(order => (
                  <tr key={order.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-mono font-bold text-white text-xs">{order.id}</div>
                      <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                        {new Date(order.created_at).toLocaleString('en-MY', {
                          timeZone: 'Asia/Kuala_Lumpur',
                          dateStyle: 'medium',
                          timeStyle: 'short',
                        })}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-slate-800 text-slate-300 flex items-center justify-center font-bold text-xs shrink-0">
                          <User className="w-3.5 h-3.5" />
                        </div>
                        <div>
                          <div className="font-semibold text-white">
                            {order.customer_name || `@${order.username}`}
                          </div>
                          <div className="text-[10px] text-slate-400 font-mono">
                            ID: {order.user_id}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-200">{order.product_name}</div>
                      {order.notes && (
                        <div className="text-[10px] text-slate-400 line-clamp-1 mt-0.5">
                          {order.notes}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-bold text-white tabular-nums">
                      {formatMYR(order.amount)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {order.receipt_url ? (
                        <button
                          type="button"
                          onClick={() => setSelectedReceiptOrder(order)}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-pink-400 hover:text-pink-300 font-medium text-[11px] transition-colors cursor-pointer border border-slate-700"
                        >
                          <Receipt className="w-3.5 h-3.5" />
                          <span>Lihat Resit</span>
                        </button>
                      ) : (
                        <span className="text-slate-400 text-[11px]">Tiada Resit</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
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
                      {order.status === 'waiting_payment' || order.status === 'pending' ? (
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            disabled={processingId === order.id}
                            onClick={() => handleApprove(order)}
                            className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1 transition-colors cursor-pointer shadow-sm disabled:opacity-50"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            <span>Lulus</span>
                          </button>
                          <button
                            type="button"
                            disabled={processingId === order.id}
                            onClick={() => setRejectingOrder(order)}
                            className="px-2 py-1 bg-red-600/20 hover:bg-red-600/30 text-red-300 rounded-lg text-xs font-medium flex items-center gap-1 transition-colors cursor-pointer border border-red-500/30 disabled:opacity-50"
                          >
                            <XCircle className="w-3.5 h-3.5" />
                            <span>Tolak</span>
                          </button>
                        </div>
                      ) : order.status === 'completed' ? (
                        <span className="text-emerald-400 text-[11px] font-medium inline-flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>Telah Dihantar</span>
                        </span>
                      ) : (
                        <span className="text-slate-400 text-[11px]">Dibatalkan</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* VIEW RECEIPT MODAL */}
      {selectedReceiptOrder && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
              <div>
                <h3 className="text-base font-bold text-white font-display">
                  Resit Bayaran #{selectedReceiptOrder.id}
                </h3>
                <p className="text-xs text-slate-400">
                  {selectedReceiptOrder.customer_name} · {formatMYR(selectedReceiptOrder.amount)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedReceiptOrder(null)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div className="rounded-xl overflow-hidden border border-slate-700 bg-slate-950 flex items-center justify-center">
                <img
                  src={selectedReceiptOrder.receipt_url}
                  alt="Bukti Bayaran"
                  className="max-h-80 w-auto object-contain"
                />
              </div>

              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-xs space-y-1">
                <div className="text-slate-400">Nota Pelanggan / Rujukan:</div>
                <div className="text-slate-200 font-mono text-[11px]">
                  {selectedReceiptOrder.notes || 'Tiada nota tambahan.'}
                </div>
              </div>

              {selectedReceiptOrder.status === 'waiting_payment' && (
                <div className="pt-2 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      const ord = selectedReceiptOrder;
                      setSelectedReceiptOrder(null);
                      handleApprove(ord);
                    }}
                    className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 cursor-pointer shadow-md"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Luluskan Bayaran & Hantar</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const ord = selectedReceiptOrder;
                      setSelectedReceiptOrder(null);
                      setRejectingOrder(ord);
                    }}
                    className="px-4 py-2.5 bg-red-600/20 hover:bg-red-600/30 text-red-300 rounded-xl text-xs font-medium cursor-pointer border border-red-500/30"
                  >
                    Tolak
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* REJECT ORDER MODAL */}
      {rejectingOrder && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
              <h3 className="text-base font-bold text-white font-display">
                Tolak Pesanan #{rejectingOrder.id}
              </h3>
              <button
                type="button"
                onClick={() => setRejectingOrder(null)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleRejectSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Sebab Penolakan (Akan dihantar kepada pelanggan via Telegram):
                </label>
                <textarea
                  rows={3}
                  required
                  value={rejectReason}
                  onChange={e => setRejectReason(e.target.value)}
                  placeholder="Contoh: Resit kabur, jumlah pemindahan kurang daripada RM15..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-slate-100 focus:outline-none focus:border-red-500"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setRejectingOrder(null)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl cursor-pointer"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-xl font-semibold cursor-pointer"
                >
                  Sahkan Penolakan
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
