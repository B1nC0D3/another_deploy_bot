import logging
import os.path
import sqlite3
from datetime import datetime

import telebot
from telebot import types

from config import TOKEN, LOGS_PATH, DB_TABLE_PROMPTS_NAME, ADMIN_ID, MAX_USERS
from gpt import ask_gpt, create_prompt, count_tokens_in_dialogue
from info import HELP_COMMANDS, DEV_COMMANDS, END_STORY
from validators import is_sessions_limit, is_tokens_limit
from database import (
    prepare_db,
    get_dialogue_for_user,
    add_record_to_table,
    get_value_from_table,
    is_value_in_table,
    count_all_tokens_from_db,
    execute_selection_query,
    get_users_amount
)
from keyboard import menu_keyboard


logging.basicConfig(
    filename=LOGS_PATH,
    level=logging.DEBUG,
    format="%(asctime)s %(message)s", filemode="w"
)

# Создаём бота
bot = telebot.TeleBot(TOKEN)

user_data = {}


# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start(message):
    user_name = message.from_user.first_name
    user_id = message.from_user.id

    user_data[user_id] = {
        'session_id': 0,
        'genre': None,
        'character': None,
        'setting': None,
        'additional_info': None,
        'state': 'регистрация',
        'test_mode': False
    }

    bot.send_message(message.chat.id, f"Привет, {user_name}! Я бот, который создаёт истории с помощью нейросети.\n"
                                      f"Мы будем писать историю поочерёдно. Я начну, а ты продолжить.\n"
                                      "Напиши /new_story, чтобы начать новую историю.\n"
                                      f"А когда ты закончишь, напиши /end.",
                     reply_markup=menu_keyboard(["/new_story"]))


# Обработчик команды /begin
@bot.message_handler(commands=['begin'])
def begin_story(message):
    user_id = message.from_user.id
    # Проверяем, что пользователь прошёл регистрацию
    if not user_data.get(user_id):
        bot.send_message(message.chat.id, 'Введи /start, тебя еще нет в регистрации на игру')
        return
    if user_data[user_id]["state"] == "регистрация":
        bot.send_message(message.chat.id, "Чтобы начать писать историю, нужно пройти небольшой опрос.\n"
                                          "Напиши /new_story и ответь на все вопросы, чтобы начать сочинять.",
                         reply_markup=menu_keyboard(['/new_story']))
        return
    user_data[user_id]["state"] = "в истории"
    # Запрашиваем ответ нейросети
    get_story(message)


@bot.message_handler(commands=['debug'])
def send_logs(message):
    if message.from_user.id == ADMIN_ID:
        if os.path.exists(LOGS_PATH):
            with open(LOGS_PATH, "rb") as f:
                bot.send_document(message.chat.id, f, reply_markup=menu_keyboard(HELP_COMMANDS + DEV_COMMANDS))
        else:
            bot.send_message(message.chat.id, f"Файл {LOGS_PATH} не найден :(")


@bot.message_handler(commands=['debug_mode_on'])
def debug_mode_on(message):
    user_id = message.from_user.id
    if user_data.get(user_id):
        user_data[user_id]['test_mode'] = True
        bot.send_message(message.chat.id, "Тестовый режим включён")


@bot.message_handler(commands=['debug_mode_off'])
def debug_mode_off(message):
    user_id = message.from_user.id
    if user_data.get(user_id):
        user_data[user_id]['test_mode'] = False
        bot.send_message(message.chat.id, "Тестовый режим выключен")


@bot.message_handler(commands=['all_tokens'])
def send_tokens(message):
    # if message.from_user.id == ADMIN_ID:
    try:
        all_tokens = count_all_tokens_from_db()
        bot.send_message(
            message.chat.id,
            f'За все время использования бота\n'
            f'Израсходовано токенов - {all_tokens}',
            reply_markup=menu_keyboard(['/new_story'] + DEV_COMMANDS)
        )
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f'Произошла ошибка при получении информации о токенах: {e}'
        )
        logging.debug(f'Произошла ошибка при получении информации о токенах: {e}')


@bot.message_handler(commands=['end'])
def end_the_story(message):
    user_id = message.from_user.id
    if not is_value_in_table(DB_TABLE_PROMPTS_NAME, 'user_id', user_id):
        bot.send_message(message.chat.id, "Ты ещё не начал историю. Напиши /begin, чтобы начать.",
                         reply_markup=menu_keyboard(['/begin']))
        return

    story_handler(message, 'end')
    bot.send_message(message.chat.id, "Спасибо, что писал со мной историю!", reply_markup=menu_keyboard(
        ['/new_story', '/whole_story', '/all_tokens', '/debug']
    ))


@bot.message_handler(commands=['whole_story'])
def get_the_whole_story(message):
    user_id = message.from_user.id

    session_id = None
    if is_value_in_table(DB_TABLE_PROMPTS_NAME, 'user_id', user_id):
        row: sqlite3.Row = get_value_from_table('session_id', user_id)
        session_id = row['session_id']

    if not session_id:
        bot.send_message(message.chat.id, "Ты ещё не начал историю."
                                          "\nНапиши /begin, чтобы начать.",
                         reply_markup=menu_keyboard(['/begin']))
        return

    collection: sqlite3.Row = get_dialogue_for_user(user_id, session_id)
    whole_story = ''
    for row in collection:
        whole_story += row['content'] + "\n"

    sql_query = f'SELECT content FROM {DB_TABLE_PROMPTS_NAME} where user_id = ? and role = ? order by date'
    data = (user_id, "system")
    prompt = execute_selection_query(sql_query, data)
    whole_story = whole_story.replace(prompt[0]['content'], '')

    bot.send_message(message.chat.id, "Вот история, которая у нас пока получилась:")
    bot.send_message(message.chat.id, whole_story, reply_markup=menu_keyboard(
        [
            '/new_story',
            '/all_tokens',
            '/debug'
        ]
    ))


# Обработчик команды /new_story
@bot.message_handler(commands=['new_story'])
def registration(message):
    """Меняет статус пользователя на "в истории",
     записывает в бд и отправляет первый вопрос о жанре"""
    users_amount = get_users_amount(DB_TABLE_PROMPTS_NAME)
    if users_amount >= MAX_USERS:
        bot.send_message(message.chat.id, 'Лимит пользователей для регистрации превышен')
        return

    bot.send_message(message.chat.id, "Для начала выбери жанр своей истории:\n",
                     reply_markup=menu_keyboard(genres))
    bot.register_next_step_handler(message, handle_genre)


def handle_genre(message):
    """Записывает ответ на вопрос о жанре в бд и отправляет следующий вопрос о персонаже"""
    user_id = message.from_user.id
    # считывает ответ на предыдущий вопрос
    genre = message.text
    # Если пользователь отвечает что-то не то, то отправляет ему вопрос ещё раз
    if genre not in genres:
        bot.send_message(message.chat.id, "Выбери один из предложенных на клавиатуре жанров:",
                         reply_markup=menu_keyboard(genres))
        bot.register_next_step_handler(message, handle_genre)
        return
    # обновляет данные пользователя
    user_data[user_id]['genre'] = genre
    user_data[user_id]['state'] = 'в истории'
    # отправляет следующий вопрос
    bot.send_message(message.chat.id, "Выбери главного героя:",
                     reply_markup=menu_keyboard(characters))
    bot.register_next_step_handler(message, handle_character)


def handle_character(message):
    """Записывает ответ на вопрос о персонаже в бд и отправляет следующий вопрос о сеттинге"""
    user_id = message.from_user.id
    # считывает ответ на предыдущий вопрос
    character = message.text
    # Если пользователь отвечает что-то не то, то отправляет ему вопрос ещё раз
    if character not in characters:
        bot.send_message(message.chat.id, "Выбери одного из предложенных на клавиатуре персонажей:",
                         reply_markup=menu_keyboard(characters))
        bot.register_next_step_handler(message, handle_character)
        return
    # обновляет данные пользователя в бд
    user_data[user_id]['character'] = character
    settings_string = "\n".join([f"{name}: {description}" for name, description in settings.items()])
    # отправляет следующий вопрос
    bot.send_message(message.chat.id, "Выбери сеттинг:\n" + settings_string,
                     reply_markup=menu_keyboard(settings.keys()))
    bot.register_next_step_handler(message, handle_setting)


def handle_setting(message):
    """Записывает ответ на вопрос о сеттинге в бд и отправляет следующий вопрос о доп. информации"""
    user_id = message.from_user.id
    # Считывает ответ на предыдущий вопрос
    user_setting = message.text
    # Если пользователь отвечает что-то не то, то отправляет ему вопрос ещё раз
    if user_setting not in settings:
        settings_string = "\n".join([f"{name}: {description}" for name, description in settings.items()])
        bot.send_message(message.chat.id, "Выбери один из предложенных на клавиатуре сеттингов:\n" + settings_string,
                         reply_markup=menu_keyboard(settings.keys()))
        bot.register_next_step_handler(message, handle_setting)
        return
    # Обновляет данные пользователя в бд
    user_data[user_id]['setting'] = user_setting
    user_data[user_id]['state'] = 'регистрация пройдена'
    # Отправляет следующий вопрос
    bot.send_message(message.chat.id, "Если ты хочешь, чтобы мы учли ещё какую-то информацию, "
                                      "напиши её сейчас. Или ты можешь сразу переходить "
                                      "к истории написав /begin.",
                     reply_markup=menu_keyboard(["/begin"]))

    bot.register_next_step_handler(message, handle_add_info)


def handle_add_info(message):
    """Записывает ответ на вопрос о доп. информации в бд"""
    user_id = message.from_user.id
    # Считывает ответ на предыдущий вопрос
    additional_info = message.text

    if additional_info == "/begin":
        begin_story(message)
    else:
        # Обновляет данные пользователя в бд
        user_data[user_id]['additional_info'] = additional_info
        # Отправляет следующий вопрос
        bot.send_message(message.chat.id, "Спасибо! Всё учтём :)\n"
                                          "Напиши /begin, чтобы начать писать историю.",
                         reply_markup=menu_keyboard(["/begin"]))


@bot.message_handler(content_types=['text'])
def story_handler(message: types.Message, mode='continue'):
    user_id: int = message.from_user.id
    user_answer: str = message.text

    if mode == 'end':
        user_answer = END_STORY

    row: sqlite3.Row = get_value_from_table('session_id', user_id)
    collection: list = get_dialogue_for_user(user_id, row['session_id'])
    collection.append({'role': 'user', 'content': user_answer})

    tokens: int = count_tokens_in_dialogue(collection)
    if is_tokens_limit(message, tokens, bot):
        return

    add_record_to_table(
        user_id,
        'user',
        user_answer,
        datetime.now(),
        tokens,
        row['session_id']
    )

    if is_tokens_limit(message, tokens, bot):
        return

    gpt_text, result_for_test = ask_gpt(collection, mode)

    collection: list = get_dialogue_for_user(user_id, row['session_id'])
    collection.append({'role': 'assistant', 'content': gpt_text})
    tokens: int = count_tokens_in_dialogue(collection)

    add_record_to_table(
        user_id,
        'assistant',
        gpt_text,
        datetime.now(),
        tokens,
        row['session_id']
    )

    if not user_data[user_id]['test_mode']:
        bot.send_message(message.chat.id, gpt_text, reply_markup=menu_keyboard(['/end']))
    else:
        bot.send_message(message.chat.id, result_for_test, reply_markup=menu_keyboard(['/end']))


# Обработчик для генерирования вопроса
@bot.message_handler(content_types=['text'])
def get_story(message: types.Message):
    user_id: int = message.from_user.id

    if is_sessions_limit(message, bot):
        return

    session_id = 1
    if is_value_in_table(DB_TABLE_PROMPTS_NAME, 'user_id', user_id):
        row: sqlite3.Row = get_value_from_table('session_id', user_id)
        session_id = row['session_id'] + 1

    user_story = create_prompt(user_data, message.from_user.id)

    collection: list = get_dialogue_for_user(user_id, session_id)
    collection.append({'role': 'system', 'content': user_story})
    tokens: int = count_tokens_in_dialogue(collection)

    bot.send_message(message.chat.id, "Генерирую...")

    add_record_to_table(
        user_id,
        'system',
        user_story,
        datetime.now(),
        tokens,
        session_id
    )

    collection: list = get_dialogue_for_user(user_id, session_id)
    gpt_text, result_for_test = ask_gpt(collection)
    collection.append({'role': 'assistant', 'content': gpt_text})

    tokens: int = count_tokens_in_dialogue(collection)
    if is_tokens_limit(message, tokens, bot):
        return

    add_record_to_table(
        user_id,
        'assistant',
        gpt_text,
        datetime.now(),
        tokens,
        session_id
    )

    if gpt_text is None:
        bot.send_message(
            message.chat.id,
            "Не могу получить ответ от GPT :(",
            reply_markup=menu_keyboard(HELP_COMMANDS)
        )

    elif gpt_text == "":
        bot.send_message(
            message.chat.id,
            "Не могу сформулировать решение :(",
            reply_markup=menu_keyboard(HELP_COMMANDS)
        )
        logging.info(f"TELEGRAM BOT: Input: {message.text}\nOutput: Error: нейросеть вернула пустую строку")

    else:
        if not user_data[user_id]['test_mode']:
            msg = bot.send_message(message.chat.id, gpt_text)
        else:
            msg = bot.send_message(message.chat.id, result_for_test)
        bot.register_next_step_handler(msg, story_handler)


# Создаём базы данных или подключаемся к существующей
prepare_db(True)
bot.infinity_polling()
