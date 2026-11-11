/**
 * Pure business logic for Berry Store Admin Control Center
 * Decoupled from UI for fast unit testing with node:test
 */

export interface Order {
  id: string;
  user_id: number;
  username: string;
  product_id: string;
  variant_id?: string;
  product_name: string;
  amount: number;
  status: 'pending' | 'waiting_payment' | 'completed' | 'rejected' | 'cancelled';
  created_at: string;
  updated_at: string;
  receipt_url?: string;
  notes?: string;
}

export interface ProductVariant {
  id: string;
  product_id: string;
  variant_name: string;
  stock: number;
  price: number;
  duration?: string;
  description?: string;
}

export interface Product {
  id: string;
  name: string;
  category: string;
  price: number;
  stock: number;
  duration?: string;
  description: string;
  auto_delivery: boolean;
  is_active: boolean;
  status: 'active' | 'inactive' | 'archived';
  image_url?: string;
  variants?: ProductVariant[];
}

export interface WalletTransaction {
  id: number;
  user_id: number;
  kind: 'topup' | 'debit' | 'refund' | 'adjustment';
  amount: number;
  balance_after: number;
  reference?: string;
  idempotency_key: string;
  created_at: string;
  note?: string;
}

/**
 * Validates if order status transition is allowed
 */
export function canTransitionOrderStatus(
  current: Order['status'],
  next: Order['status']
): { allowed: boolean; reason?: string } {
  if (current === next) {
    return { allowed: false, reason: 'Order already has this status' };
  }

  if (current === 'completed') {
    return { allowed: false, reason: 'Completed orders cannot be modified to prevent duplicate fulfillment' };
  }

  if (current === 'cancelled' && next !== 'pending') {
    return { allowed: false, reason: 'Cancelled orders can only be reopened to pending' };
  }

  const validTransitions: Record<Order['status'], Order['status'][]> = {
    pending: ['waiting_payment', 'completed', 'rejected', 'cancelled'],
    waiting_payment: ['completed', 'rejected', 'cancelled'],
    rejected: ['pending', 'waiting_payment'],
    cancelled: ['pending'],
    completed: [],
  };

  const allowed = validTransitions[current]?.includes(next) ?? false;
  return {
    allowed,
    reason: allowed ? undefined : `Cannot transition from ${current} to ${next}`,
  };
}

/**
 * Calculates updated wallet balance idempotently
 */
export function calculateWalletTransaction(
  currentBalance: number,
  kind: WalletTransaction['kind'],
  amount: number
): { valid: boolean; balanceAfter: number; error?: string } {
  if (amount <= 0 && (kind === 'topup' || kind === 'refund')) {
    return { valid: false, balanceAfter: currentBalance, error: 'Top-up and refund amounts must be positive' };
  }

  if (kind === 'debit') {
    const debitAmount = Math.abs(amount);
    if (currentBalance < debitAmount) {
      return { valid: false, balanceAfter: currentBalance, error: 'Insufficient wallet balance' };
    }
    const balanceAfter = Number((currentBalance - debitAmount).toFixed(2));
    return { valid: true, balanceAfter };
  }

  if (kind === 'topup' || kind === 'refund') {
    const balanceAfter = Number((currentBalance + amount).toFixed(2));
    return { valid: true, balanceAfter };
  }

  if (kind === 'adjustment') {
    const balanceAfter = Number((currentBalance + amount).toFixed(2));
    if (balanceAfter < 0) {
      return { valid: false, balanceAfter: currentBalance, error: 'Adjustment would result in negative balance' };
    }
    return { valid: true, balanceAfter };
  }

  return { valid: false, balanceAfter: currentBalance, error: 'Invalid transaction type' };
}

/**
 * Inventory stock check & alert level
 */
export function evaluateInventoryHealth(
  stock: number,
  lowStockThreshold: number = 5
): { status: 'out_of_stock' | 'low_stock' | 'healthy'; alert: boolean; badgeColor: string } {
  if (stock <= 0) {
    return { status: 'out_of_stock', alert: true, badgeColor: 'red' };
  }
  if (stock <= lowStockThreshold) {
    return { status: 'low_stock', alert: true, badgeColor: 'amber' };
  }
  return { status: 'healthy', alert: false, badgeColor: 'emerald' };
}

/**
 * Computes dashboard KPI aggregates from real data arrays
 */
export function computeDashboardKPIs(orders: Order[], products: Product[], walletLiabilities: number) {
  const completedOrders = orders.filter(o => o.status === 'completed');
  const pendingOrders = orders.filter(o => o.status === 'pending' || o.status === 'waiting_payment');
  const rejectedOrders = orders.filter(o => o.status === 'rejected');

  const totalRevenue = completedOrders.reduce((sum, o) => sum + (Number(o.amount) || 0), 0);

  // Time-based calculations (using ISO date strings)
  const now = new Date();
  const todayStr = now.toISOString().slice(0, 10);
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);

  const revenueToday = completedOrders
    .filter(o => o.created_at.startsWith(todayStr))
    .reduce((sum, o) => sum + (Number(o.amount) || 0), 0);

  const revenueThisWeek = completedOrders
    .filter(o => new Date(o.created_at) >= sevenDaysAgo)
    .reduce((sum, o) => sum + (Number(o.amount) || 0), 0);

  const revenueThisMonth = completedOrders
    .filter(o => new Date(o.created_at) >= thirtyDaysAgo)
    .reduce((sum, o) => sum + (Number(o.amount) || 0), 0);

  const lowStockCount = products.filter(p => p.stock <= 5 && p.is_active).length;

  return {
    totalRevenue: Number(totalRevenue.toFixed(2)),
    revenueToday: Number(revenueToday.toFixed(2)),
    revenueThisWeek: Number(revenueThisWeek.toFixed(2)),
    revenueThisMonth: Number(revenueThisMonth.toFixed(2)),
    totalOrders: orders.length,
    completedOrdersCount: completedOrders.length,
    pendingOrdersCount: pendingOrders.length,
    rejectedOrdersCount: rejectedOrders.length,
    totalProducts: products.length,
    activeProductsCount: products.filter(p => p.is_active).length,
    lowStockCount,
    walletLiability: Number(walletLiabilities.toFixed(2)),
    estimatedGrossProfit: Number((totalRevenue * 0.42).toFixed(2)), // Avg margin 42% for digital services
  };
}

/**
 * Format currency in Malaysian Ringgit (MYR)
 */
export function formatMYR(amount: number): string {
  return new Intl.NumberFormat('en-MY', {
    style: 'currency',
    currency: 'MYR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount).replace('MYR', 'RM');
}
