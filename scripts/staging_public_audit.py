"""Unauthenticated checks on the named staging host only. Never contacts production."""
import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import httpx

ORIGIN = 'https://berry-gemini-admin-staging.onrender.com'
MENUS = {
    'dashboard': ['dashboard/overview'], 'shop': ['shop/products','shop/categories'],
    'orders': ['orders'], 'credentials': ['credentials'], 'customers': ['customers'],
    'ai-studio': ['ai/tools'], 'ai-models': ['ai/models'], 'wallets': ['wallet'],
    'bot-settings': ['bot-settings'], 'broadcast': ['broadcast'],
    'referrals': ['referrals'], 'monitoring': ['system/health','system/audit-logs'],
}

async def run():
    semaphore = asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
        async def check(menu, endpoints):
            async with semaphore:
                route = '/dashboard' if menu == 'dashboard' else '/dashboard/' + menu
                try:
                    page = await client.get(ORIGIN + route)
                    html_ok = page.status_code == 200 and 'Berry Store Admin Control Center' in page.text
                    guards = []
                    for endpoint in endpoints:
                        response = await client.get(ORIGIN + '/api/admin/v1/' + endpoint)
                        guards.append({'endpoint': endpoint, 'http_status': response.status_code,
                                       'result': 'PASS' if response.status_code == 401 else 'FAIL'})
                    return {'menu': menu, 'route': route,
                            'html_result': 'PASS' if html_ok else 'FAIL',
                            'html_http_status': page.status_code,
                            'compiled_scripts': re.findall(r'src="(/assets/[^"]+\.js)"', page.text),
                            'unauthenticated_api_guards': guards,
                            'authenticated_browser_e2e': 'BLOCKED',
                            'blocker': 'Owner staging session not available. No business data or authenticated page was inspected.'}
                except httpx.HTTPError as error:
                    return {'menu': menu, 'result': 'FAIL', 'error_type': type(error).__name__,
                            'authenticated_browser_e2e': 'BLOCKED'}
        return {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'origin': ORIGIN,
                'scope': 'Unauthenticated staging HTTP checks only; this is not authenticated browser E2E.',
                'menus': await asyncio.gather(*(check(menu, paths) for menu, paths in MENUS.items()))}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = asyncio.run(run())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
