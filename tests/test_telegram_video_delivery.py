import unittest
import httpx
from telegram_video_delivery import TelegramVideoDelivery
from video_myr_worker import JobError

class DeliveryTests(unittest.TestCase):
    def transport(self, handler):
        return TelegramVideoDelivery('fixture-token',client=httpx.Client(transport=httpx.MockTransport(handler)))
    def test_confirmed_correct_recipient(self):
        d=self.transport(lambda r:httpx.Response(200,json={'ok':True,'result':{'message_id':1,'chat':{'id':900000088}}}))
        self.assertEqual(d.send(900000088,'video','https://fal.media/fixture.mp4'),1)
        d.close()
    def test_wrong_recipient_and_negative_ack_held(self):
        for payload in ({'ok':True,'result':{'message_id':1,'chat':{'id':123}}},{'ok':False}):
            d=self.transport(lambda r:httpx.Response(200,json=payload))
            with self.assertRaises(JobError):d.send(900000088,'video','https://fal.media/fixture.mp4')
            d.close()
    def test_error_redacts_token(self):
        d=self.transport(lambda r:httpx.Response(500))
        with self.assertRaises(JobError) as error:d.send(900000088,'video','https://fal.media/fixture.mp4')
        self.assertNotIn('fixture-token',str(error.exception))
        self.assertIsNone(error.exception.__cause__)
        d.close()
    def test_untrusted_url_never_sent(self):
        calls=[]
        d=self.transport(lambda r:calls.append(r))
        with self.assertRaises(JobError):d.send(900000088,'video','http://127.0.0.1/video')
        self.assertEqual(calls,[])
        d.close()
