"""Server-only Telegram transport. No token lookup, request or logging on import."""
import httpx
from video_myr_worker import JobError, trusted_result_url


class TelegramVideoDelivery:
    def __init__(self, token, *, client=None):
        if not isinstance(token,str) or not token.strip():
            raise JobError('Dedicated bot configuration required')
        self._token=token
        self._client=client

    def send(self, user_id, tool_key, result_url):
        if type(user_id) is not int or user_id<=0 or tool_key!='video':
            raise JobError('Invalid video recipient')
        result_url=trusted_result_url(result_url)
        if self._client is None:
            self._client=httpx.Client(timeout=60,follow_redirects=False)
        try:
            response=self._client.post('https://api.telegram.org/bot'+self._token+'/sendVideo',
                json={'chat_id':user_id,'video':result_url,'supports_streaming':True})
            response.raise_for_status()
            payload=response.json()
            result=payload['result']
            if (payload.get('ok') is not True or type(result.get('message_id')) is not int
                    or result['message_id']<=0 or result.get('chat',{}).get('id')!=user_id):
                raise ValueError()
            return result['message_id']
        except (httpx.HTTPError,ValueError,KeyError,TypeError):
            # Never include an HTTP exception: its URL contains the bot token.
            raise JobError('Telegram delivery unconfirmed; reconcile before another send') from None

    def close(self):
        if self._client is not None:
            self._client.close()
