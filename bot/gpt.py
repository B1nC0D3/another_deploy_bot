import os
import sqlite3

import requests
import json
import logging
import time

from config import LOGS_PATH, GPT_MODEL, MAX_MODEL_TOKENS, MODEL_TEMPERATURE, SYSTEM_PROMPT, FOLDER_ID, API_TOKEN
from info import CONTINUE_STORY, END_STORY

TOKEN_PATH = 'creds/gpt_token.json'
FOLDER_ID_PATH = 'creds/gpt_folder_id.txt'

logging.basicConfig(filename=LOGS_PATH, level=logging.DEBUG,
                    format="%(asctime)s %(message)s", filemode="w")


# Для локальных тестов
# token = 't1.9euelZqdi4yNiZPIjsvLy--YveuelZqczcyWjcjMzpebi8_Pkp2WnrXehpzRnJCSj4qLmtGLmdKckJKPioua0pKai56bnoue0oye.eqwFIlsPvXuBMHHGvXimvCtOFjCeFpw_HaXQrtEzwPs_66V3yG2XIVRr44J5Y073jw4RyXAXWJzLgvZNRejyBw'
# folder_id = ''


# Подсчитывает количество токенов в сессии
def count_tokens_in_dialogue(messages: list) -> int:
    token, folder_id = API_TOKEN, FOLDER_ID
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    data = {
       "modelUri": f"gpt://{folder_id}/yandexgpt/latest",
       "maxTokens": MAX_MODEL_TOKENS,
       "messages": []
    }

    for row in messages:
        data["messages"].append(
            {
                "role": row["role"],
                "text": row["content"]
            }
        )

    return len(
        requests.post(
            "https://llm.api.cloud.yandex.net/foundationModels/v1/tokenizeCompletion",
            json=data,
            headers=headers
        ).json()["tokens"]
    )


def create_prompt(user_data, user_id):
    prompt = SYSTEM_PROMPT
    prompt += (f"\nНапиши начало истории в стиле {user_data[user_id]['genre']} "
              f"с главным героем {user_data[user_id]['character']}. "
              f"Вот начальный сеттинг: \n{user_data[user_id]['setting']}. \n"
              "Начало должно быть коротким, 1-3 предложения.\n")

    if user_data[user_id]['additional_info']:
        prompt += (f"Так же пользователь попросил учесть "
                   f"следующую дополнительную информацию: {user_data[user_id]['additional_info']}")

    prompt += 'Не пиши никакие подсказки пользователю, что делать дальше. Он сам знает'

    return prompt


def create_new_token():
    """Создание нового токена"""
    metadata_url = "http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token"
    headers = {"Metadata-Flavor": "Google"}

    token_dir = os.path.dirname(TOKEN_PATH)
    if not os.path.exists(token_dir):
        os.makedirs(token_dir)

    try:
        response = requests.get(metadata_url, headers=headers)
        if response.status_code == 200:
            token_data = response.json()
            # Добавляем время истечения токена к текущему времени
            token_data['expires_at'] = time.time() + token_data['expires_in']
            with open(TOKEN_PATH, "w") as token_file:
                json.dump(token_data, token_file)
            logging.info("Token created")
        else:
            logging.error(f"Failed to retrieve token. Status code: {response.status_code}")
    except Exception as e:
        logging.error(f"An error occurred while retrieving token: {e}")


def get_creds():
    """Получение токена и folder_id из yandex cloud command line interface"""
    try:
        with open(TOKEN_PATH, 'r') as f:
            d = json.load(f)
            expiration = d['expires_at']
        if expiration < time.time():
            create_new_token()
    except:
        create_new_token()

    with open(TOKEN_PATH, 'r') as f:
        d = json.load(f)
        token = d["access_token"]

    with open(FOLDER_ID_PATH, 'r') as f:
        folder_id = f.read().strip()

    return token, folder_id


def ask_gpt(collection, mode='continue'):
    """Запрос к Yandex GPT"""

    # Получаем токен и folder_id, так как время жизни токена 12 часов
    token, folder_id = get_creds()

    url = f"https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    data = {
        "modelUri": f"gpt://{folder_id}/{GPT_MODEL}/latest",
        "completionOptions": {
            "stream": False,
            "temperature": MODEL_TEMPERATURE,
            "maxTokens": MAX_MODEL_TOKENS
        },
        "messages": []
    }

    for row in collection:
        content = row['content']

        # Добавляем дополнительный текст к сообщению пользователя в зависимости от режима
        if mode == 'continue' and row['role'] == 'user':
            content += '\n' + CONTINUE_STORY
        elif mode == 'end' and row['role'] == 'user':
            content += '\n' + END_STORY


        data["messages"].append(
                {
                    "role": row["role"],
                    "text": content
                }
            )

    result_for_test_mode = 'Empty message for test mode'
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 200:
            logging.debug(f"Response {response.json()} Status code:{response.status_code} Message {response.text}")
            result = f"Status code {response.status_code}. Подробности см. в журнале."
            return result, result_for_test_mode
        result = response.json()['result']['alternatives'][0]['message']['text']
        test_text = f"Input: \n{content}\nOutput: \n" + f"{response.json()}"
        result_for_test_mode = test_text
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        result = "Произошла непредвиденная ошибка. Подробности см. в журнале."

    return result, result_for_test_mode


if __name__ == '__main__':
    pass
