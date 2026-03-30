from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def confirmation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
        InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no"),
    )
    return builder.as_markup()


def result_actions_keyboard(is_paid: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buttons = [
        InlineKeyboardButton(text="📥 Скачать PDF", callback_data="export_pdf"),
    ]
    if is_paid:
        buttons.append(
            InlineKeyboardButton(text="📊 В Google Sheets", callback_data="export_sheets"),
        )
    builder.row(*buttons)
    return builder.as_markup()


def change_proposal_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Принять изменения", callback_data="accept_changes"),
        InlineKeyboardButton(text="❌ Оставить как было", callback_data="reject_changes"),
    )
    return builder.as_markup()


def lead_consent_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Понятно, продолжаем", callback_data="lead_consent_ok"),
        InlineKeyboardButton(text="Отмена", callback_data="lead_consent_cancel"),
    )
    return builder.as_markup()
