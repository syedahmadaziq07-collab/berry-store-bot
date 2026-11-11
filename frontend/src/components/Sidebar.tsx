import React from 'react';
import {
  LayoutDashboard,
  ShoppingBag,
  PackageCheck,
  KeyRound,
  Users,
  Sparkles,
  Cpu,
  Wallet,
  Bot,
  Send,
  Gift,
  Activity,
  LogOut,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
} from 'lucide-react';

export type PageId =
  | 'dashboard'
  | 'shop'
  | 'orders'
  | 'credentials'
  | 'customers'
  | 'ai-studio'
  | 'ai-models'
  | 'wallets'
  | 'bot-settings'
  | 'broadcast'
  | 'referrals'
  | 'monitoring';

interface SidebarProps {
  currentPage: PageId;
  onSelectPage: (page: PageId) => void;
  onLogout: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  pendingOrdersCount?: number;
  lowStockCount?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentPage,
  onSelectPage,
  onLogout,
  collapsed,
  onToggleCollapse,
  pendingOrdersCount = 0,
  lowStockCount = 0,
}) => {
  const navItems = [
    { id: 'dashboard' as PageId, label: 'Dashboard', icon: LayoutDashboard, section: 'CORE' },
    { id: 'shop' as PageId, label: 'Browse Shop', icon: ShoppingBag, badge: lowStockCount > 0 ? `${lowStockCount} low` : undefined, badgeColor: 'bg-amber-500/20 text-amber-300' },
    { id: 'orders' as PageId, label: 'Orders', icon: PackageCheck, badge: pendingOrdersCount > 0 ? String(pendingOrdersCount) : undefined, badgeColor: 'bg-pink-500/20 text-pink-300' },
    { id: 'credentials' as PageId, label: 'Credentials & Auto', icon: KeyRound },
    { id: 'customers' as PageId, label: 'Customers', icon: Users },
    { id: 'ai-studio' as PageId, label: 'Berry AI Studio', icon: Sparkles, section: 'AI ENGINE' },
    { id: 'ai-models' as PageId, label: 'AI Model Catalog', icon: Cpu },
    { id: 'wallets' as PageId, label: 'AI Wallets & Ledger', icon: Wallet },
    { id: 'bot-settings' as PageId, label: 'Bot Control Center', icon: Bot, section: 'TELEGRAM' },
    { id: 'broadcast' as PageId, label: 'Broadcast Campaign', icon: Send },
    { id: 'referrals' as PageId, label: 'Referrals & Vouchers', icon: Gift },
    { id: 'monitoring' as PageId, label: 'System Monitoring', icon: Activity, section: 'SYSTEM' },
  ];

  return (
    <aside
      className={`bg-slate-900 border-r border-slate-800 flex flex-col justify-between transition-all duration-300 shrink-0 z-30 select-none ${
        collapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* Brand Header */}
      <div>
        <div className="h-16 flex items-center justify-between px-4 border-b border-slate-800">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-pink-500 to-purple-600 p-0.5 shrink-0 shadow-md shadow-pink-500/20">
              <img
                src="/images/berry_store_logo_1794372740187.jpg"
                alt="Berry Store"
                className="w-full h-full rounded-[10px] object-cover"
                onError={(e) => {
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />
            </div>
            {!collapsed && (
              <div className="leading-tight truncate">
                <span className="font-bold text-white tracking-tight font-display block text-sm">
                  BERRY STORE
                </span>
                <span className="text-[11px] font-medium text-pink-400 block">
                  Admin Control Center
                </span>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        {/* Navigation Items */}
        <nav className="p-3 space-y-1 overflow-y-auto max-h-[calc(100vh-140px)]">
          {navItems.map((item, idx) => {
            const Icon = item.icon;
            const isActive = currentPage === item.id;
            return (
              <React.Fragment key={item.id}>
                {!collapsed && item.section && idx !== 0 && (
                  <div className="text-[10px] font-bold text-slate-400 tracking-wider px-3 pt-3 pb-1">
                    {item.section}
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => onSelectPage(item.id)}
                  title={collapsed ? item.label : undefined}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-pink-500/15 text-pink-300 font-semibold border border-pink-500/30 shadow-sm shadow-pink-500/10'
                      : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
                  }`}
                >
                  <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-pink-400' : 'text-slate-400'}`} />
                  {!collapsed && (
                    <span className="truncate flex-1 text-left">{item.label}</span>
                  )}
                  {!collapsed && item.badge && (
                    <span className={`text-[11px] font-mono px-2 py-0.5 rounded-md ${item.badgeColor || 'bg-slate-800 text-slate-300'}`}>
                      {item.badge}
                    </span>
                  )}
                </button>
              </React.Fragment>
            );
          })}
        </nav>
      </div>

      {/* Footer Profile & Logout */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-900/50">
        {!collapsed && (
          <div className="flex items-center justify-between px-3 py-2 mb-2 bg-slate-950/60 rounded-xl border border-slate-800">
            <div className="truncate">
              <div className="text-xs font-semibold text-slate-200">Owner Admin</div>
              <div className="text-[11px] text-pink-400">@berrystorrel</div>
            </div>
            <a
              href="https://t.me/berrystorrel"
              target="_blank"
              rel="noreferrer"
              className="text-slate-400 hover:text-pink-400 transition-colors p-1"
              title="Open Telegram Channel"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        )}
        <button
          type="button"
          onClick={onLogout}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-xs font-medium text-slate-300 hover:text-red-300 hover:bg-red-500/10 transition-colors cursor-pointer"
        >
          <LogOut className="w-4 h-4" />
          {!collapsed && <span>Log Keluar (Logout)</span>}
        </button>
      </div>
    </aside>
  );
};
