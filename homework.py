import logging
import os
import sys
import time
import typing
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

RETRY_PERIOD = 600  # время в секундах (10 минут)
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}


def func_logger(func):
    """Логгирование запуска функций с параметрами."""

    def inner(*args, **kwargs):
        """Подфункция."""
        logger = logging.getLogger(__name__)
        ret = func(*args, **kwargs)
        logger.info(
            f'Функция {func.__name__} принимает {args, kwargs} и даёт {ret}',
        )
        return ret

    return inner


@func_logger
def send_message(bot: telegram.Bot, message: str) -> str:
    """Отправка сообщений ботом bot.

    Args:
        bot: бот с токеном 'TELEGRAM_TOKEN'.
        message: сообщение, отправляемое ботом.

    Raises:
        ошибка, когда бот не отправил сообщение.

    Returns:
        сообщение.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except telegram.error.TelegramError:
        logging.exception(f'Бот не отправил {message}.')
        raise RequestExceptionError(f'Бот не отправил {message}.')
    logging.debug(f'Бот успешно отправил: {message}')
    return message


def get_api_answer(current_timestamp: int) -> HttpResponse:
    """Получение API ответа от эндпоинта.

    Args:
        current_timestamp: текущая дата.

    Returns:
        ответ API.

    Raises:
        HTTPError: сервер недоступен.
        ConnectionError: проблема с ответом сервера.
    """
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': current_timestamp},
        )
    except requests.exceptions.RequestException as error:
        raise ConnectionError(f'Проблема с ответом сервера: {error}')
    if response.status_code != HTTPStatus.OK:
        raise requests.exceptions.HTTPError(
            f'Ошибка {response.status_code}',
        )
    return response.json()


def check_response(response: HttpResponse) -> HttpResponse:
    """Проверка ответа API на корректность.

    Args:
        response: API ответ.

    Returns:
        ответ API.

    Raises:
        TypeError: ошибка типа данных.
    """
    if (
        isinstance(response, dict)
        and all(key in response for key in ('current_date', 'homeworks'))
        and isinstance(response['homeworks'], list)
    ):
        return response['homeworks']
    raise TypeError('Ответ API не корректен')


def parse_status(homework: typing.Dict[str, str]) -> str:
    """Проверка статуса работы, полученного в API.

    Args:
        homework: один элемент списка домашних работ.

    Returns:
        один из вердиктов словаря с вердиктами.

    Raises:
        KeyError: ключ не найден.
        RequestExceptionError: статус домашней работы неопределен.
    """
    try:
        name, status = homework['homework_name'], homework['status']
    except KeyError as error:
        message = f'Ключ {error} не найден в информации о домашней работе'
        logging.getLogger(__name__).error(message)
        raise KeyError(message)
    try:
        verdict = HOMEWORK_VERDICTS[status]
    except KeyError as error:
        message = f'Статус домашней работы неопределен: {error}'
        logging.getLogger(__name__).error(message)
        raise RequestExceptionError(message)
    return f'Изменился статус проверки работы "{name}". {verdict}'


def check_tokens() -> None:
    """Проверка токенов.

    Raises:
        Ошибка о том, что токен не найден.

    Returns:
        None.
    """
    for name in ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID'):
        if globals().get(name) is None:
            logging.critical('Токен {} не найден'.format(name))
            raise RequestExceptionError('Токен {} не найден'.format(name))
    return None


def main():
    """Основной принцип работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    old_error = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response.get('current_date')
            logging.debug('Начало проверки ответа сервера')
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                send_message(bot, message)
            logging.debug('Пауза')
        except Exception as error:
            logging.error(error)
            if error != old_error:
                message = f'Сбой в работе программы: {error}'
                send_message(bot, message)
                old_error = error
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        filename=Path('HOMEWORK_BOT', 'homework.log'),
        format='%(asctime)s, %(levelname)s, %(message)s',
        filemode='w',
    )
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            '%(asctime)s, %(levelname)s, %(message)s, %(funcName)s',
        ),
    )
    main()
