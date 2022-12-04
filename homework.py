import logging
import os
import sys
import time
from http import HTTPStatus
from pathlib import Path

import requests
import telegram
from django.http import HttpResponse
from dotenv import load_dotenv

from exceptions import RequestExceptionError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600  # время в секундах(10 минут)
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}


def send_message(bot: telegram.Bot, message: str) -> str:
    """Отправка сообщений ботом bot.

    Args:
        bot: бот с токеном 'TELEGRAM_TOKEN'.
        message: сообщение, отправляемое ботом.

    Returns:
        str.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug(f"Бот успешно отправил: {message}")
    except telegram.error.TelegramError as error:
        logging.exception(f"Бот не отправил {message}. Ошибка {error}")
    return message


def get_api_answer(current_timestamp: int) -> HttpResponse:
    """Получение API ответа от эндпоинта.

    Args:
        current_timestamp: текущая дата.

    Returns:
        HttpResponse.

    Raises:
        HTTPError: сервер недоступен.
        ConnectionError: проблема с ответом сервера.
    """
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={"from_date": current_timestamp},
        )
        if response.status_code != HTTPStatus.OK:
            raise requests.exceptions.HTTPError(
                f"Ошибка {response.status_code}",
            )
        return response.json()
    except requests.exceptions.RequestException as error:
        raise ConnectionError(f"Проблема с ответом сервера: {error}")


def check_response(response: HttpResponse) -> HttpResponse:
    """Проверка ответа API на корректность.

    Args:
        response: API ответ.

    Returns:
        HttpResponse.

    Raises:
        KeyError: ошибка значения.
        TypeError: ошибка типа данных.
    """
    if not isinstance(response, dict):
        raise TypeError('Ответ от эндпоинта пришел не в формате словаря')
    if 'homeworks' not in response:
        raise KeyError('Данных homeworks нет в ответе эндпоинта')
    if (
        isinstance(response, dict)
        and all(key for key in ('current_date', 'homeworks'))
        and isinstance(response["homeworks"], list)
    ):
        return response["homeworks"]
    raise TypeError("Ответ API не корректен")


def parse_status(homework: dict) -> str:
    """Проверка статуса работы, полученного в API.

    Args:
        homework: один элемент списка домашних работ.

    Returns:
        str.

    Raises:
        KeyError: ключ не найден.
        RequestExceptionError: статус домашней работы неопределен.
    """
    try:
        name = homework['homework_name']
        status = homework['status']
    except KeyError as error:
        message = f'Ключ {error} не найден в информации о домашней работе'
        logging.getLogger(__name__).error(message)
        raise KeyError(message)
    try:
        verdict = HOMEWORK_VERDICTS[status]
        logging.getLogger(__name__).info('Сообщение готово для отправки')
    except KeyError as error:
        message = f'Статус домашней работы неопределен: {error}'
        logging.getLogger(__name__).error(message)
        raise RequestExceptionError(message)
    return f'Изменился статус проверки работы "{name}". {verdict}'


def check_tokens() -> bool:
    """Проверка токенов.

    Returns:
        bool.
    """
    flag = True
    for name in ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID'):
        if globals()[name] is None:
            logging.critical('Токен {} не найден'.format(name))
            flag = False
    return flag


def main():
    """Основной принцип работы бота."""
    if not check_tokens():
        quit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    old_error = ""
    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response.get("current_date")
            logging.debug("Начало проверки ответа сервера")
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                send_message(bot, message)
            logging.debug("Пауза")
        except Exception as error:
            logging.error(error)
            if error != old_error:
                message = f"Сбой в работе программы: {error}"
                send_message(bot, message)
                old_error = error
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == "__main__":
    Path(__file__)
    logging.basicConfig(
        level=logging.DEBUG,
        filename="my_logger.log",
        format="%(asctime)s, %(levelname)s, %(message)s",
        filemode="w",
    )
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("%(asctime)s, %(levelname)s, %(message)s"),
    )
    main()
