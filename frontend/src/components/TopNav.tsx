import React from 'react';
import { PageId } from './Sidebar';
import { RefreshCw, Globe, Moon, Sun, CloudUpload, Bell } from 'lucide-react';

interface TopNavProps {
  currentPage: PageId;
  onRefresh: () => void;
  isRefreshing: boolean;
  onOpenDeployModal: () => void;
  isDarkMode: boolean;
  onToggleTheme: () => void;
  language: 'en' | 'bm';
  onToggleLanguage: () => void;
  onMobileMenuToggle: () => void;
}

const pageTitles: Record<PageId, { en: string; bm: string }> = {
  dashboard: { en: 'Dashboard Overview', bm: 'Ringkasan Papan Pemuka' },
  shop: { en: 'Browse Shop & Products', bm: 'Pengurusan Kedai & Produk' },
  orders: { en: 'Order Management', bm: 'Pengurusan Pesanan' },
  credentials: { en: 'Digital Credentials & Auto Delivery', bm: 'Inventori Kredensial & Penghantaran Auto' },
  customers: { en: 'Customer Directory', bm: 'Direktori Pelanggan' },
  'ai-studio': { en: 'Berry AI Studio Tools', bm: 'Alatan Berry AI Studio' },
  'ai-models': { en: 'AI Model Catalog & Margin', bm: 'Katalog Model AI & Margin' },
  wallets: { en: 'AI Wallets & Ledger', bm: 'Dompet AI & Lejar Baki' },
  'bot-settings': { en: 'Telegram Bot Control Center', bm: 'Pusat Kawalan Bot Telegram' },
  broadcast: { en: 'Telegram Marketing Broadcast', bm: 'Siaran Pemasaran Telegram' },
  referrals: { en: 'Referral Program & Vouchers', bm: 'Program Rujukan & Baucar' },
  monitoring: { en: 'System Monitoring & Audit', bm: 'Pemantauan Sistem & Log Audit' },
};

export const TopNav: React.FC<TopNavProps> = ({
  currentPage,
  onRefresh,
  isRefreshing,
  onOpenDeployModal,
  isDarkMode,
  onToggleTheme,
  language,
  onToggleLanguage,
  onMobileMenuToggle,
}) => {
  const currentTitle = pageTitles[currentPage]?.[language] || 'Admin';

  return (
    <header className="h-16 bg-slate-900/90 backdrop-blur-md border-b border-slate-800 px-4 md:px-6 flex items-center justify-between gap-4 sticky top-0 z-20">
      {/* Zone 1: Breadcrumb Trail & Mobile Hamburger */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          type="button"
          onClick={onMobileMenuToggle}
          className="md:hidden p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800"
          aria-label="Open mobile menu"
        >
          <span className="sr-only">Menu</span>
          <div className="w-5 h-4 flex flex-col justify-between">
            <span className="w-full h-0.5 bg-current rounded-full" />
            <span className="w-full h-0.5 bg-current rounded-full" />
            <span className="w-full h-0.5 bg-current rounded-full" />
          </div>
        </button>

        <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-xs md:text-sm font-medium min-w-0">
          <span className="text-slate-400 font-mono hidden sm:inline">Berry Store</span>
          <span className="text-slate-600 hidden sm:inline">/</span>
          <h2 className="text-slate-100 font-semibold truncate max-w-[120px] sm:max-w-none font-display">
            {currentTitle}
          </h2>
        </nav>
      </div>

      {/* Zone 2: System Status Indicators */}
      <div className="hidden lg:flex items-center gap-4 text-xs">
        <div className="flex items-center gap-1.5 text-slate-300 bg-slate-950/60 px-2.5 py-1 rounded-md border border-slate-800">
          <span className="w-2 h-2 rounded-full bg-slate-500" />
          <span className="font-mono">Dashboard staging · polling disabled</span>
        </div>
        <div className="flex items-center gap-1.5 text-slate-300 bg-slate-950/60 px-2.5 py-1 rounded-md border border-slate-800">
          <span className="w-2 h-2 rounded-full bg-pink-400" />
          <span className="font-mono">MYR (Asia/Kuala_Lumpur)</span>
        </div>
      </div>

      {/* Zone 3: Actions & Controls */}
      <div className="flex items-center gap-2 shrink-0">
        <button
          type="button"
          onClick={onRefresh}
          disabled={isRefreshing}
          title="Refresh Data"
          className="p-2 text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin text-pink-400' : ''}`} />
        </button>

        <button
          type="button"
          onClick={onToggleLanguage}
          title={`Switch to ${language === 'en' ? 'Bahasa Melayu' : 'English'}`}
          className="px-2.5 py-1 text-xs font-semibold text-slate-300 hover:text-white bg-slate-800/80 hover:bg-slate-800 rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer"
        >
          <Globe className="w-3.5 h-3.5 text-pink-400" />
          <span>{language === 'en' ? 'EN' : 'BM'}</span>
        </button>

        <button
          type="button"
          onClick={onToggleTheme}
          title={isDarkMode ? 'Light Mode' : 'Dark Mode'}
          className="p-2 text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
        >
          {isDarkMode ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-indigo-300" />}
        </button>

        {/* Primary Deployment & Render Sync Button */}
        <button
          type="button"
          onClick={onOpenDeployModal}
          className="flex items-center gap-2 px-3 py-1.5 bg-gradient-to-r from-pink-600 to-purple-600 hover:from-pink-500 hover:to-purple-500 text-white text-xs font-medium rounded-lg shadow-sm shadow-pink-600/20 transition-all cursor-pointer whitespace-nowrap shrink-0"
        >
          <CloudUpload className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Deploy / Render</span>
          <span className="sm:hidden">Deploy</span>
        </button>
      </div>
    </header>
  );
};
