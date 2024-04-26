import os

from dotenv import load_dotenv


load_dotenv()

LOGS_PATH = 'logs.txt'

DB_DIR = 'db'
DB_NAME = 'gpt_helper.db'
DB_TABLE_PROMPTS_NAME = 'prompts'

ADMIN_ID = ''
TOKEN = os.getenv('TG_TOKEN')
API_TOKEN = 't1.9euelZqVyZnKks-Rzo6SnJCJl5LNle3rnpWaisaTlpDNm8yTjYmYlpiayMvl8_dQRwRQ-e9mCExc_d3z9xB2AVD572YITFz9zef1656VmsjNjZiRlMmNnZORjs2elouY7_zF656VmsjNjZiRlMmNnZORjs2elouYveuelZrMjcbNzZzOy5OJipOZy4mXzbXehpzRnJCSj4qLmtGLmdKckJKPioua0pKai56bnoue0oye.CpqGiwwWxmVqHINDEpcsctuGOjzer0qw_2-PRfIiD3y9A6lSczWbqz1xRUsgGA1ol3tIL4KokHDHojBdJ4oYDg'

FOLDER_ID = 'b1ghfb4epm2t95ql7k0d'
MAX_USERS = 3
# Модель, которую используем
GPT_MODEL = 'yandexgpt'
# Ограничение на выход модели в токенах
MAX_MODEL_TOKENS = 1000
# Креативность GPT (от 0 до 1)
MODEL_TEMPERATURE = 0.6

# Каждому пользователю даем 3 сеанса общения, каждый сеанс это новый help_with
MAX_SESSIONS = 3
# Каждому пользователю выдаем 1500 токенов на 1 сеанс общения
MAX_TOKENS_IN_SESSION = 2500

SYSTEM_PROMPT = (
    "Ты пишешь историю вместе с человеком. "
    "Историю вы пишете по очереди. Начинает человек, а ты продолжаешь. "
    "Если это уместно, ты можешь добавлять в историю диалог между персонажами. "
    "Диалоги пиши с новой строки и отделяй тире. "
    "Не пиши никакого пояснительного текста в начале, а просто логично продолжай историю"
)
