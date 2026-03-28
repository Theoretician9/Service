from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="\u26a1 \u0411\u044b\u0441\u0442\u0440\u044b\u0439 \u0437\u0430\u043f\u0443\u0441\u043a", callback_data="quick_start"),
        InlineKeyboardButton(text="\ud83d\udcc1 \u041c\u043e\u0438 \u043f\u0440\u043e\u0435\u043a\u0442\u044b", callback_data="my_projects"),
    )
    builder.row(
        InlineKeyboardButton(text="\ud83d\udce6 \u041c\u043e\u0438 \u0430\u0440\u0442\u0435\u0444\u0430\u043a\u0442\u044b", callback_data="my_artifacts"),
        InlineKeyboardButton(text="\ud83d\udcb3 \u0422\u0430\u0440\u0438\u0444", callback_data="my_plan"),
    )
    builder.row(
        InlineKeyboardButton(text="\u2753 \u041f\u043e\u043c\u043e\u0449\u044c", callback_data="help"),
    )
    return builder.as_markup()


def miniservices_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="\ud83c\udfaf \u041f\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430 \u0446\u0435\u043b\u0435\u0439 \u2014 1 \u043a\u0440\u0435\u0434\u0438\u0442", callback_data="ms:goal_setting"))
    builder.row(InlineKeyboardButton(
        text="\ud83d\udd0d \u0412\u044b\u0431\u043e\u0440 \u043d\u0438\u0448\u0438 \u2014 2 \u043a\u0440\u0435\u0434\u0438\u0442\u0430", callback_data="ms:niche_selection"))
    builder.row(InlineKeyboardButton(
        text="\ud83d\udce6 \u041f\u043e\u0438\u0441\u043a \u043f\u043e\u0441\u0442\u0430\u0432\u0449\u0438\u043a\u043e\u0432 \u2014 2 \u043a\u0440\u0435\u0434\u0438\u0442\u0430", callback_data="ms:supplier_search"))
    builder.row(InlineKeyboardButton(
        text="\ud83d\udcac \u0421\u043a\u0440\u0438\u043f\u0442\u044b \u043f\u0440\u043e\u0434\u0430\u0436 \u2014 2 \u043a\u0440\u0435\u0434\u0438\u0442\u0430", callback_data="ms:sales_scripts"))
    builder.row(InlineKeyboardButton(
        text="\ud83d\udce2 \u041f\u0440\u043e\u0434\u0430\u044e\u0449\u0438\u0435 \u043e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u044f \u2014 2 \u043a\u0440\u0435\u0434\u0438\u0442\u0430", callback_data="ms:ad_creation"))
    builder.row(InlineKeyboardButton(
        text="\ud83d\udc65 \u041f\u043e\u0438\u0441\u043a \u043a\u043b\u0438\u0435\u043d\u0442\u043e\u0432 \u2014 3 \u043a\u0440\u0435\u0434\u0438\u0442\u0430 \ud83d\udd12", callback_data="ms:lead_search"))
    builder.row(InlineKeyboardButton(text="\u2190 \u041d\u0430\u0437\u0430\u0434", callback_data="back_to_menu"))
    return builder.as_markup()


def onboarding_start_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="\u041f\u043e\u0435\u0445\u0430\u043b\u0438 \u2192", callback_data="onboarding_start"))
    return builder.as_markup()


def onboarding_complete_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="\u26a1 \u041f\u043e\u043f\u0440\u043e\u0431\u043e\u0432\u0430\u0442\u044c \u0441\u0435\u0439\u0447\u0430\u0441", callback_data="quick_start"),
        InlineKeyboardButton(text="\ud83d\udcc1 \u0421\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u0440\u043e\u0435\u043a\u0442", callback_data="create_project"),
    )
    return builder.as_markup()


def upgrade_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="\ud83d\ude80 \u041f\u0435\u0440\u0435\u0439\u0442\u0438 \u043d\u0430 Paid", callback_data="upgrade"))
    return builder.as_markup()


def result_actions_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="\ud83d\udcca \u0412 Google Sheets", callback_data="export_sheets"),
        InlineKeyboardButton(text="\ud83d\udce5 \u0421\u043a\u0430\u0447\u0430\u0442\u044c PDF", callback_data="export_pdf"),
    )
    builder.row(InlineKeyboardButton(text="\ud83d\udcc1 \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0432 \u043f\u0440\u043e\u0435\u043a\u0442", callback_data="attach_to_project"))
    return builder.as_markup()
