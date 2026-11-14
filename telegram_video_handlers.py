"""Handlers called by the existing Telegram bot. UI and runtime remain fail closed."""
import asyncio
from video_myr_worker import JobError


def runtime(update, context):
    flow=context.application.bot_data.get('berry_video_flow')
    if flow is None:
        raise JobError('AI Video belum diaktifkan. Tiada caj dikenakan.')
    flow.authorize(update.effective_user.id,update.effective_chat.type=='private')
    return flow


async def request_prompt(update,context):
    flow=runtime(update,context)
    if context.user_data.get('pending_receipt'):
        raise JobError('Selesaikan penghantaran resit dahulu.')
    context.user_data['ai_video_flow']={'stage':'live_prompt','ratio':'16:9'}
    await update.callback_query.message.reply_text('✏️ Hantar prompt video. Model, tetapan, harga dan baki akan dipaparkan sebelum Confirm.')


async def prepare_prompt(update,context,keyboard_factory=None):
    state=context.user_data.get('ai_video_flow')
    if not isinstance(state,dict) or state.get('stage')!='live_prompt':return False
    if context.user_data.get('pending_receipt'):return False
    flow=runtime(update,context)
    ticket=await asyncio.to_thread(flow.prepare,update.effective_user.id,update.update_id,
                                  update.message.text or '',state['ratio'])
    if keyboard_factory is None:
        from telegram import InlineKeyboardButton,InlineKeyboardMarkup
        keyboard_factory=lambda rows:InlineKeyboardMarkup([
            [InlineKeyboardButton(text,callback_data=data) for text,data in row] for row in rows])
    payload=ticket['payload'];q=payload['quote'];ident=ticket['ticket_id']
    await update.message.reply_text(
        f"🎬 {payload['label']}\n{payload['settings_label']}\n"
        f"Harga: {q['credits']:,} Berry Credits (RM{q['debit_cents']/100:.2f})\n"
        f"Baki: {ticket['balance_credits']} Berry Credits\n"
        f"Prompt: {payload['prompt']}\n\nConfirm untuk debit dan generation; Cancel untuk batal. Quote mempunyai tempoh luput.",
        reply_markup=keyboard_factory([[('✅ Confirm','ai_video_confirm:'+ident),
                                        ('❌ Cancel','ai_video_cancel:'+ident)]]))
    context.user_data.pop('ai_video_flow',None)
    return True


async def consent_callback(update,context,action,ticket_id):
    flow=runtime(update,context)
    if action not in ('confirm','cancel'):raise JobError('Tindakan tidak sah')
    result=await asyncio.to_thread(getattr(flow,action),update.effective_user.id,ticket_id)
    job=result.get('job') or {};state=job.get('state',result['state'])
    messages={
        'cancelled':'✅ Dibatalkan. Tiada generation baharu dihantar.',
        'refunded':'✅ Dibatalkan sebelum submission. Kredit telah dipulangkan sekali sahaja.',
        'queued':'⏳ Video dalam proses. Sistem akan menghantar video apabila siap.',
        'delivered':'✅ Video telah dihantar.',
        'submission_unknown':'⚠️ Status submission sedang disemak. Tiada request atau refund berulang dibuat.',
        'delivery_unknown':'⚠️ Penghantaran sedang disemak. Video tidak dihantar semula secara automatik.',
        'submitting':'⏳ Submission sedang diproses; pembatalan tidak lagi dijamin.',
        'delivering':'⏳ Penghantaran sedang diproses.',
        'reserved':'⏳ Job direkodkan; submission menunggu semakan kos/bajet. Cancel masih tersedia.',
    }
    await update.callback_query.message.reply_text(messages.get(state,'⏳ Job direkodkan dan sedang disemak.'))
    return result
