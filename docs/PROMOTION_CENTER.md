# Berry Store Promotion Center — operator guide

## Open the dashboard

1. Open `/dashboard` on the Berry Store Render service.
2. Connect with the existing `DASHBOARD_ADMIN_SECRET` (never paste it in public chat).
3. Choose **Promotion Center** in the sidebar.

## Destinations

- **Telegram Group / Channel:** save its `https://t.me/...` link and a numeric chat ID such as `-1001234567890`, or public `@channel_username` where supported. Add the Berry Store bot to the target chat and give it posting permission. Tick *posting permitted* only after verifying the group's rules. Use **Test Connection** to check visibility; a successful test does not guarantee send permission.
- **Google Form Confession:** save its `https://docs.google.com/forms/.../viewform` or `https://forms.gle/...` URL, optional Gmail label (not password), and `entry.123...` IDs obtained using the form's **Get pre-filled link** feature. The dashboard generates an **Open prefilled form** button. The operator must review and submit it. Google Forms' official API does not provide a submit-respondent-answer endpoint, and this system does not bypass authentication, CAPTCHA or posting restrictions.
- A destination marked inactive or not permitted cannot be selected for a campaign.

## Connect up to 3 Threads accounts

Create a Meta developer app with the Threads API use case and request the necessary `threads_basic` / `threads_content_publish` permissions. Configure the callback URL in the Meta app exactly as:

`https://YOUR-RENDER-HOST/api/dashboard/promotion/threads/callback`

Configure these **server-side Render** environment variables (do not put them in frontend JS):

| Variable | Meaning |
| --- | --- |
| `THREADS_APP_ID` | Meta Threads App ID |
| `THREADS_APP_SECRET` | Meta Threads App Secret |
| `PROMOTION_TOKEN_KEY` | Separate random secret, at least 32 characters; retain across deploys |
| `PROMOTION_PUBLIC_URL` | Canonical HTTPS Render origin, with no trailing slash |

Click **Connect Threads Account** and complete OAuth on each account separately. The access token is encrypted before being saved in the server-only Supabase table; only username and token-expiry metadata return to the UI. **Disconnect** wipes the stored token while keeping delivery history. Tokens that expire need reconnection.

This version supports **text Threads posts** (max 500 characters) and optional per-account captions. Media publishing and Threads engagement metrics need an additional release.

## Campaigns, sending and reports

1. Write a campaign name and message, or use a saved template / caption idea.
2. Tick only permitted destinations and connected Threads accounts. Add optional account-specific Threads captions.
3. Leave schedule empty for immediate dispatch or pick a time in your local browser timezone.
4. Review the confirmation dialog and click Send. The backend queues the request. Nothing is sent while editing.
5. The worker claims due campaigns, posts to permissioned Telegram destinations / connected Threads accounts, and marks Google Forms as **manual** with a prefilled link. It records one status per destination, including errors and external message/post IDs.
6. **Retry Failed Only** resends only confirmed failed deliveries. Unknown outcomes are not retried automatically to avoid duplicates. A campaign is blocked from sending an identical message to the same destination within 12 hours.

## Deployment and verification

- Apply `docs/sql/berry_promotion_center.sql` to the production Supabase project, once. Tables are scoped by tenant and restricted to `service_role`; anon/authenticated cannot read them.
- Push `promotion_center.py`, `bot.py`, `dashboard.html`, requirements, and tests to the Render-connected `main` branch, then manual-deploy the Render bot service (auto-deploy currently off).
- Tests: `python -m unittest tests.test_promotion_center tests.test_berry_visual_menu tests.test_berry_dashboard_catalog_details`.
- **Do not** test by sending live promotions to groups without their permission. Use unit tests, Test Connection and a private test group you control.
