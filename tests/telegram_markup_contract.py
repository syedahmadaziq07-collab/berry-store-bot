"""Run explicitly in the pinned Telegram CI environment, separate from admin deps."""
import unittest
import test_telegram_video_flow as fixtures
from telegram_video_handlers import prepare_prompt,request_prompt

class MarkupContract(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.HandlerTests.setUp
    async def test_actual_telegram_markup_serializes(self):
        await request_prompt(self.update,self.context)
        self.assertTrue(await prepare_prompt(self.update,self.context))
        markup=self.message.reply_text.call_args.kwargs['reply_markup'].to_dict()
        buttons=markup['inline_keyboard'][0]
        self.assertEqual(len(buttons),2)
        self.assertTrue(buttons[0]['callback_data'].startswith('ai_video_confirm:'))
        self.assertTrue(buttons[1]['callback_data'].startswith('ai_video_cancel:'))
        self.assertLessEqual(len(buttons[0]['callback_data'].encode()),64)
