# Atomic top-up checkout and payment contract verification

Checkout previously queried active orders then inserted separately. Concurrent Telegram
callbacks could both see no active order and create duplicates. `berry_create_topup_order`
now locks the request key and tenant/user, reuses active orders, derives prices on the server,
and stores a durable Telegram-update idempotency key. The bot does not retry an ambiguous
write automatically. A deliberate later callback reuses the existing active order.

Completed callbacks do not open another QR, and orders waiting for approval explicitly say
not to pay again. Existing shop orders block a new top-up checkout. This serializes top-up
callbacks; the legacy shop order creation path does not yet share this lock, so mixed
shop/top-up simultaneous checkout still needs a common order reservation policy before launch.

The wallet ledger replay now also compares the original reference, preventing a key from
being reused for a different job with the same user/amount/type.

## Actual isolated database validation

Only cirsdvkfkvypprnmyykk was migrated. A minimal staging-only tenants/orders schema enables
the repository's actual `ai_wallet_apply_transaction` and `berry_approve_topup_order` functions
to run against dummy records. This is not a full copy of production's database schema and
does not certify production schema compatibility.

`docs/sql/verify_staging_payment_contract.sql` passed and rolled back all its data. It checks
checkout replay/ownership, receipt gate, unauthorized rejection, approval credit once, closed
callback replay, MYR debit/refund idempotency, reference conflicts, sub-cent rejection,
insufficient funds and ledger reconciliation.

Eight simultaneous checkout RPC calls created one order. Eight simultaneous approval calls
all returned successfully, with one RM5 synthetic top-up and one ledger entry. The concurrency
fixture is retained in staging under tenant `dddddddd-4444-4444-8444-444444444444`, user
`900000004`; approver `900000099` is also a dummy identity. These are test numbers, not money
received from a bank or customer transactions. No bank transfer or provider purchase occurred.

119 Python tests pass, including executing the actual Telegram checkout handler body with
mocked transport/effects. Live Telegram and receipt/bank validation are still not E2E tested.

## Release gates

Customer top-up remains disabled. No environment flag was enabled and production is unchanged.
The checkout SQL requires the private request table and new RPC before the bot change can
be deployed to a customer service. Real receipt verification, operator authorization,
concurrent mixed shop/top-up checkout, delivery notifications and full browser/Telegram E2E
remain necessary. A receipt image is not proof of settled bank payment.
