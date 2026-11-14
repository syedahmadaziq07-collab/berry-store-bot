import { loadAdminModules, MENU_REQUIREMENTS, MENU_OPTIONAL, MODULE_ENDPOINTS, ModuleId, ModuleResults, pageFromPath } from './utils/admin-data';
import { apiFetch, setCsrfToken } from './api';
import React, { useState, useEffect, useRef } from 'react';
import { LoginView } from './components/LoginView';
import { Sidebar, PageId } from './components/Sidebar';
import { TopNav } from './components/TopNav';
import { DashboardOverview } from './components/DashboardOverview';
import { ShopManagement } from './components/ShopManagement';
import { OrderManagement } from './components/OrderManagement';
import { CredentialInventory } from './components/CredentialInventory';
import { CustomerDirectory } from './components/CustomerDirectory';
import { AIStudioManagement } from './components/AIStudioManagement';
import { WalletManagement } from './components/WalletManagement';
import { TelegramBotControl } from './components/TelegramBotControl';
import { BroadcastMarketing } from './components/BroadcastMarketing';
import { TurnitinManagement } from './components/TurnitinManagement';
import { SystemMonitoring } from './components/SystemMonitoring';
import { RenderIntegrationModal } from './components/RenderIntegrationModal';
import {
  Category,
  Product,
  Order,
  CredentialItem,
  Customer,
  AITool,
  AIModel,
  UserWallet,
  WalletTransaction,
  BotSettings,
  AuditLog,
} from './types/store';

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [currentPage, setCurrentPage] = useState<PageId>(() => pageFromPath(window.location.pathname));
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [language, setLanguage] = useState<'en' | 'bm'>('bm');
  const [isDeployModalOpen, setIsDeployModalOpen] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Application Data States
  const [kpis, setKpis] = useState<any>({
    totalRevenue: 0,
    revenueToday: 0,
    revenueThisWeek: 0,
    revenueThisMonth: 0,
    totalOrders: 0,
    completedOrdersCount: 0,
    pendingOrdersCount: 0,
    totalProducts: 0,
    lowStockCount: 0,
    aiWalletLiability: 0,
    estimatedGrossProfit: 0,
  });
  const [orders, setOrders] = useState<Order[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [credentials, setCredentials] = useState<CredentialItem[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [aiTools, setAiTools] = useState<AITool[]>([]);
  const [aiModels, setAiModels] = useState<AIModel[]>([]);
  const [wallets, setWallets] = useState<UserWallet[]>([]);
  const [transactions, setTransactions] = useState<WalletTransaction[]>([]);
  const [walletTotalBalance, setWalletTotalBalance] = useState(0);
  const [botSettings, setBotSettings] = useState<BotSettings>({
    welcome_message: '',
    browse_shop_enabled: '',
    ai_studio_enabled: '',
    referral_enabled: '',
    maintenance_mode: '',
    banner_url: '',
    banner_file_id: '',
    payment_qr_url: '',
    payment_qr_file_id: '',
    support_username: '',
    announcement: '',
    required_channel: '',
    required_channel_url: '',
    min_topup_amount: '',
    referral_reward_rm: '',
  });
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [broadcasts, setBroadcasts] = useState<any[]>([]);
  const [revenueTrend, setRevenueTrend] = useState<any[]>([]);
  const [categoryRevenue, setCategoryRevenue] = useState<Record<string, number>>({});
  const [systemHealth, setSystemHealth] = useState<any>(null);
  const [moduleResults, setModuleResults] = useState<ModuleResults>({});
  const loadSequence = useRef(0);
  const activeLoad = useRef<AbortController | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  // Check existing session on boot
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const res = await fetch('/api/admin/v1/auth/me');
        if (res.ok) {
          const data = await res.json();
          if (data.authenticated) {
            setIsAuthenticated(true);
            setCurrentUser(data.user);
            setCsrfToken(data.csrfToken);
            fetchAllData();
            return;
          }
        }
      } catch (_) {}
      setIsAuthenticated(false);
    };
    checkAuth();
  }, []);

  const navigate = (page: PageId) => {
    setCurrentPage(page);
    window.history.pushState({}, '', page === 'dashboard' ? '/dashboard' : `/dashboard/${page}`);
  };
  useEffect(() => {
    const onPopState = () => setCurrentPage(pageFromPath(window.location.pathname));
    window.addEventListener('popstate', onPopState);
    return () => { window.removeEventListener('popstate', onPopState); activeLoad.current?.abort(); };
  }, []);

  // Each module can fail independently. A previous response cannot overwrite a newer refresh.
  const fetchAllData = async () => {
    const sequence = ++loadSequence.current;
    activeLoad.current?.abort();
    const controller = new AbortController();
    activeLoad.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 25000);
    setIsRefreshing(true);
    setModuleResults(Object.fromEntries(Object.keys(MODULE_ENDPOINTS).map(id => [id, {status: 'loading'}])));
    try {
      const results = await loadAdminModules(fetch, controller.signal);
      if (sequence !== loadSequence.current) return;
      if (Object.values(results).some(r => r?.status === 'error' && r.httpStatus === 401)) {
        setIsAuthenticated(false); setCsrfToken(''); setModuleResults({}); return;
      }
      setModuleResults(results);
      const data = (id: ModuleId): any => results[id]?.status === 'ready' ? (results[id] as any).data : null;
      const overview = data('overview');
      if (overview) { setKpis(overview.kpis); setRevenueTrend(overview.revenueTrend || []); setCategoryRevenue(overview.categoryRevenue || {}); }
      setProducts(data('products') || []); setCategories(data('categories') || []);
      setOrders(data('orders') || []); setCredentials(data('credentials') || []);
      setCustomers(data('customers') || []); setAiTools(data('tools') || []); setAiModels(data('models') || []);
      const wallet = data('wallet');
      setWallets(wallet?.wallets || []); setTransactions(wallet?.transactions || []);
      setWalletTotalBalance(wallet?.totalBalance ?? 0);
      if (data('settings')) setBotSettings(data('settings'));
      setBroadcasts(data('broadcasts') || []); setAuditLogs(data('audit') || []);
      setSystemHealth(data('health'));
    } finally {
      window.clearTimeout(timeout);
      if (sequence === loadSequence.current) setIsRefreshing(false);
    }
  };

  const handleLoginSuccess = (data: any) => {
    setCsrfToken(data.csrfToken);
    setIsAuthenticated(true);
    setCurrentUser(data.user);
    fetchAllData();
    showToast('Log masuk admin berjaya.');
  };

  useEffect(() => {
    const onError = (event: Event) => showToast(`Ralat: ${(event as CustomEvent).detail}`);
    const onExpired = () => { setIsAuthenticated(false); setCsrfToken(''); };
    const onUnhandled = (event: PromiseRejectionEvent) => { showToast(`Ralat: ${event.reason?.message || 'Permintaan gagal'}`); event.preventDefault(); };
    window.addEventListener('api-error', onError);
    window.addEventListener('session-expired', onExpired);
    window.addEventListener('unhandledrejection', onUnhandled);
    return () => { window.removeEventListener('api-error', onError); window.removeEventListener('session-expired', onExpired); window.removeEventListener('unhandledrejection', onUnhandled); };
  }, []);

  const handleLogout = async () => {
    try {
      await apiFetch('/api/admin/v1/auth/logout', { method: 'POST' });
    } catch (err: any) { showToast(err.message); return; }
    setCsrfToken('');
    activeLoad.current?.abort();
    loadSequence.current += 1;
    setModuleResults({});
    setIsAuthenticated(false);
    setCurrentUser(null);
  };

  // Order status update
  const handleUpdateOrderStatus = async (orderId: string, status: Order['status'], reason?: string) => {
    try {
      const res = await apiFetch(`/api/admin/v1/orders/${orderId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, reason }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Gagal mengemaskini pesanan');
      }
      showToast(`Pesanan #${orderId} dikemaskini kepada: ${status}`);
      fetchAllData();
    } catch (err: any) {
      showToast(`Ralat: ${err.message}`);
    }
  };

  // Save Product
  const handleSaveProduct = async (productData: Partial<Product>) => {
    const isEdit = Boolean(productData.id);
    const url = isEdit ? `/api/admin/v1/shop/products/${productData.id}` : '/api/admin/v1/shop/products';
    const method = isEdit ? 'PUT' : 'POST';

    const res = await apiFetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(productData),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Gagal menyimpan produk');
    }
    showToast(`Produk ${productData.name} berjaya disimpan`);
    fetchAllData();
  };

  const handleDeleteProduct = async (id: string) => {
    const res = await apiFetch(`/api/admin/v1/shop/products/${id}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Produk dipadam');
      fetchAllData();
    }
  };

  const handleAdjustStock = async (id: string, newStock: number) => {
    const res = await apiFetch(`/api/admin/v1/shop/products/${id}/stock`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ newStock }),
    });
    if (res.ok) {
      showToast(`Baki stok dikemaskini kepada ${newStock}`);
      fetchAllData();
    }
  };

  // Categories
  const handleSaveCategory = async (catData: Partial<Category>) => {
    const isEdit = Boolean(catData.id);
    const url = isEdit ? `/api/admin/v1/shop/categories/${catData.id}` : '/api/admin/v1/shop/categories';
    const method = isEdit ? 'PUT' : 'POST';

    const res = await apiFetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(catData),
    });
    if (res.ok) {
      showToast('Kategori disimpan');
      fetchAllData();
    }
  };

  const handleDeleteCategory = async (id: string) => {
    const res = await apiFetch(`/api/admin/v1/shop/categories/${id}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Kategori dipadam');
      fetchAllData();
    }
  };

  // Credentials
  const handleImportCredentials = async (productId: string, variantId: string | null, rawText: string) => {
    const res = await apiFetch('/api/admin/v1/credentials', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, variant_id: variantId, raw_credentials: rawText }),
    });
    if (res.ok) {
      const d = await res.json();
      showToast(`${d.importedCount} akaun kredensial berjaya ditambah`);
      fetchAllData();
    }
  };

  const handleDeleteCredential = async (id: string) => {
    const res = await apiFetch(`/api/admin/v1/credentials/${id}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Kredensial dipadam');
      fetchAllData();
    }
  };

  // Customers
  const handleUpdateCustomer = async (id: number, notes: string, status: Customer['status']) => {
    const res = await apiFetch(`/api/admin/v1/customers/${id}/notes`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes, status }),
    });
    if (res.ok) {
      showToast('Profil pelanggan dikemaskini');
      fetchAllData();
    }
  };

  // AI Tools
  const handleUpdateTool = async (id: string, updates: Partial<AITool>) => {
    const res = await apiFetch(`/api/admin/v1/ai/tools/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    if (res.ok) {
      showToast('Tetapan alatan AI dikemaskini');
      fetchAllData();
    }
  };

  // AI Models
  const handleUpdateModel = async (id: string, updates: Partial<AIModel>) => {
    const res = await apiFetch(`/api/admin/v1/ai/models/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    if (res.ok) {
      showToast('Katalog model AI dikemaskini');
      fetchAllData();
    }
  };

  // Wallet Adjust
  const handleAdjustBalance = async (userId: number, amount: number, kind: WalletTransaction['kind'], note: string) => {
    const res = await apiFetch('/api/admin/v1/wallet/adjust', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, amount, kind, note }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Gagal laras baki dompet');
    }
    showToast('Baki dompet berjaya dilaras dalam lejar');
    fetchAllData();
  };

  // Bot Settings
  const handleSaveBotSettings = async (updates: Partial<BotSettings>) => {
    const res = await apiFetch('/api/admin/v1/bot-settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    if (res.ok) {
      setBotSettings(await res.json());
      showToast('Tetapan bot disimpan ke Supabase');
    }
  };

  // Broadcast
  const handleSendBroadcast = async (title: string, message: string, audience: string) => {
    const res = await apiFetch('/api/admin/v1/broadcast/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, message, audience }),
    });
    if (res.ok) {
      showToast('Siaran mesej broadcast dihantar!');
      fetchAllData();
    }
  };

  // Referral Reward
  const handleUpdateReward = async (rewardRM: string) => {
    await handleSaveBotSettings({ referral_reward_rm: rewardRM });
  };

  // Toggle dark/light theme
  const handleToggleTheme = () => {
    setIsDarkMode(!isDarkMode);
    if (!isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  };

  // Loading state
  if (isAuthenticated === null) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-2 border-pink-500/20 border-t-pink-500 rounded-full animate-spin" />
          <span className="text-xs font-mono text-slate-400">Menyambung ke Berry Store Admin...</span>
        </div>
      </div>
    );
  }

  // Login view if not authenticated
  if (!isAuthenticated) {
    return <LoginView onLoginSuccess={handleLoginSuccess} />;
  }

  const required = MENU_REQUIREMENTS[currentPage] as readonly ModuleId[];
  const optional = (MENU_OPTIONAL as Partial<Record<PageId, readonly ModuleId[]>>)[currentPage] || [];
  const errors = [...required, ...optional].filter(id => moduleResults[id]?.status === 'error');
  const pageReady = required.every(id => moduleResults[id]?.status === 'ready');

  const pendingOrdersCount = orders.filter(o => o.status === 'waiting_payment' || o.status === 'pending').length;
  const lowStockCount = products.filter(p => p.stock <= 5 && p.is_active).length;

  return (
    <div className={`min-h-screen flex bg-slate-950 text-slate-100 ${isDarkMode ? 'dark' : ''}`}>
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-5 right-5 z-50 bg-slate-900 border border-pink-500/40 text-white text-xs px-4 py-2.5 rounded-xl shadow-2xl flex items-center gap-2 animate-in fade-in slide-in-from-bottom-2 duration-200">
          <span className="w-2 h-2 rounded-full bg-pink-400 animate-pulse" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Desktop Sidebar */}
      <div className="hidden md:flex">
        <Sidebar
          currentPage={currentPage}
          onSelectPage={navigate}
          onLogout={handleLogout}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
          pendingOrdersCount={pendingOrdersCount}
          lowStockCount={lowStockCount}
        />
      </div>

      {/* Mobile Drawer Overlay */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-40 bg-black/70 md:hidden backdrop-blur-sm flex">
          <div className="w-72 bg-slate-900 h-full">
            <Sidebar
              currentPage={currentPage}
              onSelectPage={(p) => {
                navigate(p);
                setMobileMenuOpen(false);
              }}
              onLogout={handleLogout}
              collapsed={false}
              onToggleCollapse={() => setMobileMenuOpen(false)}
              pendingOrdersCount={pendingOrdersCount}
              lowStockCount={lowStockCount}
            />
          </div>
          <div className="flex-1" onClick={() => setMobileMenuOpen(false)} />
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 min-h-screen overflow-x-hidden">
        <TopNav
          currentPage={currentPage}
          onRefresh={fetchAllData}
          isRefreshing={isRefreshing}
          onOpenDeployModal={() => setIsDeployModalOpen(true)}
          isDarkMode={isDarkMode}
          onToggleTheme={handleToggleTheme}
          language={language}
          onToggleLanguage={() => setLanguage(language === 'en' ? 'bm' : 'en')}
          onMobileMenuToggle={() => setMobileMenuOpen(!mobileMenuOpen)}
        />

        <main className="flex-1 p-4 md:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          <div role="status" className="mb-4 p-3 rounded-xl border border-amber-800 bg-amber-950/30 text-xs text-amber-200">{systemHealth?.mode || 'staging'} · {systemHealth?.writesEnabled ? 'Perubahan dibenarkan' : 'Data kedai dilindungi: perubahan, pembayaran dan broadcast dikunci.'}</div>
          {errors.map(id => <div key={id} role="alert" data-module={id} className="mb-3 p-3 rounded-xl border border-red-800 bg-red-950/40 text-xs text-red-200 break-words">
            {id}: {moduleResults[id]?.status === 'error' ? (moduleResults[id] as any).error : ''}
          </div>)}
          {isRefreshing && <p role="status" className="mb-4 text-xs text-pink-400">Memuatkan data sebenar...</p>}
          {!isRefreshing && !pageReady && <div className="p-6 border border-slate-800 rounded-xl text-sm text-slate-300">
            Menu ini belum dapat memaparkan data yang disahkan. Semak sambungan backend dan cuba semula.
            <button type="button" onClick={fetchAllData} className="ml-3 text-pink-400 underline">Cuba semula</button>
          </div>}
          {currentPage === 'dashboard' && pageReady && (
            <DashboardOverview
              kpis={kpis}
              orders={orders}
              products={products}
              lowStockAlerts={products.filter(p => p.stock <= 5 && p.is_active)}
              revenueTrend={revenueTrend}
              categoryRevenue={categoryRevenue}
              onNavigateToOrders={() => navigate('orders')}
              onNavigateToShop={() => navigate('shop')}
              onNavigateToAIStudio={() => navigate('ai-studio')}
              onNavigateToTurnitin={() => navigate('turnitin')}
              onApproveOrder={(id) => handleUpdateOrderStatus(id, 'completed')}
            />
          )}

          {currentPage === 'shop' && pageReady && (
            <ShopManagement
              categories={categories}
              products={products}
              onSaveProduct={handleSaveProduct}
              onDeleteProduct={handleDeleteProduct}
              onAdjustStock={handleAdjustStock}
              onSaveCategory={handleSaveCategory}
              onDeleteCategory={handleDeleteCategory}
            />
          )}

          {currentPage === 'orders' && pageReady && (
            <OrderManagement
              orders={orders}
              onUpdateOrderStatus={handleUpdateOrderStatus}
            />
          )}

          {currentPage === 'credentials' && pageReady && (
            <CredentialInventory
              credentials={credentials}
              products={products}
              onImportCredentials={handleImportCredentials}
              onDeleteCredential={handleDeleteCredential}
            />
          )}

          {currentPage === 'customers' && pageReady && (
            <CustomerDirectory
              customers={customers}
              onUpdateCustomer={handleUpdateCustomer}
            />
          )}

          {currentPage === 'ai-studio' && pageReady && (
            <AIStudioManagement
              key="tools"
              initialTab="tools"
              tools={aiTools}
              models={aiModels}
              onUpdateTool={handleUpdateTool}
              onUpdateModel={handleUpdateModel}
            />
          )}

          {currentPage === 'ai-models' && pageReady && (
            <AIStudioManagement
              key="models"
              initialTab="models"
              tools={aiTools}
              models={aiModels}
              onUpdateTool={handleUpdateTool}
              onUpdateModel={handleUpdateModel}
            />
          )}

          {currentPage === 'wallets' && pageReady && (
            <WalletManagement
              totalBalance={walletTotalBalance}
              wallets={wallets}
              transactions={transactions}
              onAdjustBalance={handleAdjustBalance}
            />
          )}

          {currentPage === 'bot-settings' && pageReady && (
            <TelegramBotControl
              settings={botSettings}
              onSaveSettings={handleSaveBotSettings}
            />
          )}

          {currentPage === 'broadcast' && pageReady && (
            <BroadcastMarketing
              broadcasts={broadcasts}
              customerCount={customers.length}
              onSendBroadcast={handleSendBroadcast}
            />
          )}

          {(currentPage === 'turnitin' || currentPage === 'referrals') && pageReady && (
            <TurnitinManagement canEdit={Boolean(systemHealth?.writesEnabled)} />
          )}

          {currentPage === 'monitoring' && pageReady && (
            <SystemMonitoring
              auditLogs={auditLogs}
              health={systemHealth}
              onRefreshHealth={fetchAllData}
            />
          )}
        </main>
      </div>

      {/* Render Integration Modal */}
      <RenderIntegrationModal
        isOpen={isDeployModalOpen}
        onClose={() => setIsDeployModalOpen(false)}
      />
    </div>
  );
}
