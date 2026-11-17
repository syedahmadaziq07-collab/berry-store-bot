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
