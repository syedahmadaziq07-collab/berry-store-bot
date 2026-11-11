export interface Category {
  id: string;
  name: string;
  emoji: string;
  description: string;
  display_order: number;
  is_active: boolean;
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
  display_order?: number;
  delivery_type?: 'automated' | 'manual';
  variants?: ProductVariant[];
}

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
  customer_name?: string;
}

export interface CredentialItem {
  id: string;
  product_id: string;
  variant_id?: string;
  credential_data: string;
  credential_data_masked?: string;
  is_used: boolean;
  order_id?: string;
  created_at: string;
}

export interface Customer {
  id: number;
  username: string;
  name: string;
  joined_at: string;
  total_orders: number;
  total_spent: number;
  wallet_balance: number;
  referral_count: number;
  status: 'active' | 'restricted' | 'blocked';
  notes?: string;
}

export interface AITool {
  id: string;
  name: string;
  category: string;
  enabled: boolean;
  provider: string;
  model_id: string;
  credit_cost: number;
  max_duration_sec: number;
  supported_ratios: string[];
  daily_limit_per_user: number;
  maintenance: boolean;
  description: string;
}

export interface AIModel {
  id: string;
  name: string;
  provider: string;
  model_id: string;
  tool_category: string;
  provider_cost: number;
  customer_price: number;
  margin_pct: number;
  enabled: boolean;
  last_verified: string;
}

export interface WalletTransaction {
  id: number;
  user_id: number;
  username?: string;
  kind: 'topup' | 'debit' | 'refund' | 'adjustment';
  amount: number;
  balance_after: number;
  reference?: string;
  idempotency_key: string;
  created_at: string;
  note?: string;
}

export interface UserWallet {
  user_id: number;
  username: string;
  balance: number;
  currency: string;
  updated_at: string;
}

export interface BotSettings {
  welcome_message: string;
  browse_shop_enabled: string;
  ai_studio_enabled: string;
  referral_enabled: string;
  maintenance_mode: string;
  banner_url: string;
  banner_file_id: string;
  payment_qr_url: string;
  payment_qr_file_id: string;
  support_username: string;
  announcement: string;
  required_channel: string;
  required_channel_url: string;
  min_topup_amount: string;
  referral_reward_rm: string;
  [key: string]: string;
}

export interface AuditLog {
  id: string;
  action: string;
  actor: string;
  details: string;
  timestamp: string;
  ip: string;
}
