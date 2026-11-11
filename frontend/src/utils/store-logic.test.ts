import test from 'node:test';
import assert from 'node:assert/strict';
import {
  canTransitionOrderStatus,
  calculateWalletTransaction,
  evaluateInventoryHealth,
  computeDashboardKPIs,
  formatMYR,
  Order,
  Product,
} from './store-logic';

test('Order status state machine prevents duplicate completion and illegal transitions', () => {
  // Pending can transition to completed or waiting_payment
  assert.equal(canTransitionOrderStatus('pending', 'completed').allowed, true);
  assert.equal(canTransitionOrderStatus('pending', 'waiting_payment').allowed, true);
  assert.equal(canTransitionOrderStatus('waiting_payment', 'completed').allowed, true);

  // Critical safeguard: Completed cannot be re-approved or changed
  const completedTransition = canTransitionOrderStatus('completed', 'completed');
  assert.equal(completedTransition.allowed, false);
  const completedToPending = canTransitionOrderStatus('completed', 'pending');
  assert.equal(completedToPending.allowed, false);

  // Same status transition rejected
  assert.equal(canTransitionOrderStatus('rejected', 'rejected').allowed, false);
});

test('Wallet transaction ledger enforces strict direction and balance integrity', () => {
  // Positive top-up
  const topup = calculateWalletTransaction(50.0, 'topup', 25.5);
  assert.equal(topup.valid, true);
  assert.equal(topup.balanceAfter, 75.5);

  // Successful debit
  const debit = calculateWalletTransaction(75.5, 'debit', 30.0);
  assert.equal(debit.valid, true);
  assert.equal(debit.balanceAfter, 45.5);

  // Overdraft prevention
  const overdraft = calculateWalletTransaction(20.0, 'debit', 50.0);
  assert.equal(overdraft.valid, false);
  assert.match(overdraft.error || '', /Insufficient wallet balance/);

  // Negative top-up rejection
  const badTopup = calculateWalletTransaction(20.0, 'topup', -10.0);
  assert.equal(badTopup.valid, false);
});

test('Inventory health correctly calculates alerts and out of stock levels', () => {
  assert.deepEqual(evaluateInventoryHealth(0), {
    status: 'out_of_stock',
    alert: true,
    badgeColor: 'red',
  });
  assert.deepEqual(evaluateInventoryHealth(3, 5), {
    status: 'low_stock',
    alert: true,
    badgeColor: 'amber',
  });
  assert.deepEqual(evaluateInventoryHealth(15, 5), {
    status: 'healthy',
    alert: false,
    badgeColor: 'emerald',
  });
});

test('Dashboard KPI aggregates correctly calculate revenues and counts', () => {
  const dummyOrders: Order[] = [
    {
      id: 'ord-1',
      user_id: 101,
      username: 'alice',
      product_id: 'p1',
      product_name: 'Netflix 1M',
      amount: 15.0,
      status: 'completed',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: 'ord-2',
      user_id: 102,
      username: 'bob',
      product_id: 'p2',
      product_name: 'Spotify 3M',
      amount: 30.0,
      status: 'completed',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: 'ord-3',
      user_id: 103,
      username: 'charlie',
      product_id: 'p3',
      product_name: 'Canva Pro',
      amount: 10.0,
      status: 'pending',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ];

  const dummyProducts: Product[] = [
    {
      id: 'p1',
      name: 'Netflix',
      category: 'Entertainment',
      price: 15.0,
      stock: 2,
      description: 'Netflix 4K',
      auto_delivery: true,
      is_active: true,
      status: 'active',
    },
    {
      id: 'p2',
      name: 'Spotify',
      category: 'Entertainment',
      price: 30.0,
      stock: 12,
      description: 'Spotify Premium',
      auto_delivery: true,
      is_active: true,
      status: 'active',
    },
  ];

  const kpis = computeDashboardKPIs(dummyOrders, dummyProducts, 120.0);
  assert.equal(kpis.totalRevenue, 45.0);
  assert.equal(kpis.completedOrdersCount, 2);
  assert.equal(kpis.pendingOrdersCount, 1);
  assert.equal(kpis.lowStockCount, 1);
  assert.equal(kpis.totalProducts, 2);
  assert.equal(kpis.walletLiability, 120.0);
});

test('formatMYR formats Malaysian Ringgit cleanly', () => {
  const formatted = formatMYR(25.5);
  assert.ok(formatted.includes('25.50'));
  assert.ok(formatted.includes('RM'));
});
