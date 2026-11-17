import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToString} from 'react-dom/server';
import {DashboardOverview} from '../components/DashboardOverview';
import {ShopManagement} from '../components/ShopManagement';
import {OrderManagement} from '../components/OrderManagement';
import {CredentialInventory} from '../components/CredentialInventory';
import {CustomerDirectory} from '../components/CustomerDirectory';
import {AIStudioManagement} from '../components/AIStudioManagement';
import {WalletManagement} from '../components/WalletManagement';
import {TelegramBotControl} from '../components/TelegramBotControl';
import {BroadcastMarketing} from '../components/BroadcastMarketing';
import {ReferralSystem} from '../components/ReferralSystem';
import {SystemMonitoring} from '../components/SystemMonitoring';
import {Sidebar} from '../components/Sidebar';
import {TopNav} from '../components/TopNav';
import {RenderIntegrationModal} from '../components/RenderIntegrationModal';
import {PromotionCenter} from '../components/PromotionCenter';

const noop = () => {};
const task = async () => {};
const kpis = {
  totalRevenue: 0, revenueToday: 0, revenueThisWeek: 0, revenueThisMonth: 0,
  totalOrders: 0, completedOrdersCount: 0, pendingOrdersCount: 0,
  totalProducts: 0, lowStockCount: 0, aiWalletLiability: 0, estimatedGrossProfit: null,
};
const settings = {
  welcome_message: '', browse_shop_enabled: 'false', ai_studio_enabled: 'false',
  referral_enabled: 'false', maintenance_mode: 'false', banner_url: '',
  payment_qr_url: '', support_username: '', announcement: '',
  required_channel: '', required_channel_url: '', min_topup_amount: '',
  referral_reward_rm: '',
};
const pages: Array<[string, unknown, Record<string, unknown>]> = [
  ['Dashboard Overview', DashboardOverview, {
    kpis, orders: [], products: [], lowStockAlerts: [], revenueTrend: [],
    categoryRevenue: {}, onNavigateToOrders: noop, onNavigateToShop: noop,
    onApproveOrder: noop,
  }],
  ['Browse Shop', ShopManagement, {
    categories: [], products: [], onSaveProduct: task, onDeleteProduct: task,
    onAdjustStock: task, onSaveCategory: task, onDeleteCategory: task,
  }],
  ['Orders', OrderManagement, {orders: [], onUpdateOrderStatus: task}],
  ['Credentials', CredentialInventory, {
    credentials: [], products: [], onImportCredentials: task, onDeleteCredential: task,
  }],
  ['Customers', CustomerDirectory, {customers: [], onUpdateCustomer: task}],
  ['AI Studio', AIStudioManagement, {
    initialTab: 'tools', tools: [], models: [], onUpdateTool: task, onUpdateModel: task,
  }],
  ['AI Catalog', AIStudioManagement, {
    initialTab: 'models', tools: [], models: [], onUpdateTool: task, onUpdateModel: task,
  }],
  ['AI Wallets', WalletManagement, {
    wallets: [], transactions: [], totalBalance: 0, onAdjustBalance: task,
  }],
  ['Bot Control Center', TelegramBotControl, {settings, onSaveSettings: task}],
  ['Broadcast Campaign', BroadcastMarketing, {
    broadcasts: [], customerCount: 0, onSendBroadcast: task,
  }],
  ['Referrals', ReferralSystem, {
    customers: [], referralRewardRM: '', onUpdateReward: task,
  }],
  ['System Monitoring', SystemMonitoring, {
    auditLogs: [], health: {status: 'degraded', database: 'not_configured'},
    onRefreshHealth: noop,
  }],
  ['Promotion Center', PromotionCenter, {}],
  ['Render Integration Modal', RenderIntegrationModal, {
    isOpen: true, onClose: noop,
  }],
];

for (const [name, Component, props] of pages) {
  test(name + ' renders without throwing on empty data', () => {
    const markup = renderToString(React.createElement(Component as React.ElementType, props));
    assert.ok(markup.length > 100, name + ' rendered empty content');
  });
}

test('sidebar shows Promotion Center and all navigation sections', () => {
  const markup = renderToString(React.createElement(Sidebar, {
    currentPage: 'promotion-center', onSelectPage: noop, onLogout: noop,
    collapsed: false, onToggleCollapse: noop,
  }));
  for (const name of ['Dashboard', 'Browse Shop', 'Orders', 'Promotion Center', 'System Monitoring'])
    assert.ok(markup.includes(name), 'missing sidebar section: ' + name);
});

test('Gemini top navigation names the promotion page', () => {
  const markup = renderToString(React.createElement(TopNav, {
    currentPage: 'promotion-center', onRefresh: noop, isRefreshing: false,
    onOpenDeployModal: noop, isDarkMode: true, onToggleTheme: noop,
    language: 'bm', onToggleLanguage: noop, onMobileMenuToggle: noop,
  }));
  assert.ok(markup.includes('Pusat Promosi Multi-Platform'));
});


const sampleProduct = {
  id: '1', name: 'Contoh Produk', category: '', price: 15.5, stock: 5,
  duration: '1 month', description: 'Contoh akaun digital', auto_delivery: true,
  is_active: true, status: 'active', variants: [
    {id: 'v1', product_id: '1', variant_name: 'Satu Bulan', stock: 5, price: 15.5},
  ],
};
const sampleOrder = {
  id: 'ORD-QA-1', user_id: 1, username: 'qa_user', product_id: '1',
  product_name: 'Contoh Produk', amount: 15.5, status: 'pending',
  created_at: '2026-11-17T08:30:00Z', updated_at: '2026-11-17T08:30:00Z',
};
const sampleCustomer = {
  id: 1, username: 'qa_user', name: 'Pengguna Ujian', joined_at: '2026-11-17T08:30:00Z',
  total_orders: 1, total_spent: 15.5, wallet_balance: 20,
  referral_count: 0, status: 'unknown', notes: '',
};
const sampleWallet = {
  user_id: 1, username: 'qa_user', balance: 20, currency: 'MYR',
  updated_at: '2026-11-17T08:30:00Z',
};
const nonEmptyPages: Array<[string, unknown, Record<string, unknown>, string]> = [
  ['Dashboard data rows', DashboardOverview, {
    kpis, orders: [sampleOrder], products: [sampleProduct],
    lowStockAlerts: [sampleProduct], revenueTrend: [{date: '2026-11-17', revenue: 15.5}],
    categoryRevenue: {}, onNavigateToOrders: noop, onNavigateToShop: noop,
    onApproveOrder: noop,
  }, 'Contoh Produk'],
  ['Shop product + variant', ShopManagement, {
    categories: [{id: 'c1', name: 'Digital', emoji: '📦', description: '', display_order: 1, is_active: true}],
    products: [sampleProduct], onSaveProduct: task, onDeleteProduct: task,
    onAdjustStock: task, onSaveCategory: task, onDeleteCategory: task,
  }, 'Contoh Produk'],
  ['Orders row', OrderManagement, {
    orders: [sampleOrder], onUpdateOrderStatus: task,
  }, 'ORD-QA-1'],
  ['Credential row', CredentialInventory, {
    credentials: [{id: 'k1', product_id: '1', variant_id: 'v1',
      credential_data: '', credential_data_masked: '••••••••', is_used: false,
      created_at: '2026-11-17T08:30:00Z'}],
    products: [sampleProduct], onImportCredentials: task, onDeleteCredential: task,
  }, 'Contoh Produk'],
  ['Customers row', CustomerDirectory, {
    customers: [sampleCustomer], onUpdateCustomer: task,
  }, 'Pengguna Ujian'],
  ['AI model rows', AIStudioManagement, {
    initialTab: 'models', tools: [], models: [{
      id: 'a1', name: 'Demo Model', provider: 'demo', model_id: 'model-a',
      tool_category: 'video', provider_cost: 0.5, customer_price: 1.5,
      margin_pct: 66.6, enabled: true, last_verified: '2026-11-17',
    }], onUpdateTool: task, onUpdateModel: task,
  }, 'Demo Model'],
  ['Wallet balances and ledger', WalletManagement, {
    wallets: [sampleWallet], transactions: [{
      id: 1, user_id: 1, username: 'qa_user', kind: 'topup', amount: 20,
      balance_after: 20, idempotency_key: 'test-only', created_at: '2026-11-17T08:30:00Z',
    }], totalBalance: 20, onAdjustBalance: task,
  }, 'qa_user'],
  ['Referral leaderboard', ReferralSystem, {
    customers: [{...sampleCustomer, referral_count: 2}],
    referralRewardRM: '1', onUpdateReward: task,
  }, 'Pengguna Ujian'],
];
for (const [name, Component, props, expected] of nonEmptyPages) {
  test(name + ' renders safely from populated API data', () => {
    const markup = renderToString(React.createElement(Component as React.ElementType, props));
    assert.ok(markup.includes(expected), name + ' did not render the expected data');
  });
}
