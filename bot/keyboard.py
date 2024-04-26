from telebot import types


# Создаёт клавиатуру с указанными кнопками
def menu_keyboard(options: list) -> types.ReplyKeyboardMarkup:
    buttons = (types.KeyboardButton(text=option) for option in options)
    keyboard = types.ReplyKeyboardMarkup(
        row_width=2,
        resize_keyboard=True,
        one_time_keyboard=True
    )
    keyboard.add(*buttons)
    return keyboard
