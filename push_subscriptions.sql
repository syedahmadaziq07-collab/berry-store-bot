-- Create push_subscriptions table for Web Push notifications
-- Run this in your Supabase SQL Editor

CREATE TABLE IF NOT EXISTS push_subscriptions (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  endpoint    TEXT NOT NULL UNIQUE,
  keys        JSONB NOT NULL,       -- { p256dh, auth }
  user_agent  TEXT,
  created_at  TIMESTAMPTZ DEFAULT now(),
  is_active   BOOLEAN DEFAULT true
);

-- Index for active subscriptions lookup
CREATE INDEX IF NOT EXISTS idx_push_subs_active ON push_subscriptions (is_active) WHERE is_active = true;

-- Allow service_role full access (RLS off for admin table)
ALTER TABLE push_subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow service_role full access" ON push_subscriptions
  FOR ALL USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');
