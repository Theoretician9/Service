from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="/cancel")]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
