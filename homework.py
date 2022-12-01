import logging
import os
import sys
import time

import requests
import telegram
from dotenv import load_dotenv

from exceptions import ExceptionError

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}


def send_message(bot, message):
    """Отправка сообщений ботом."""
    try:
        logging.debug(f'Бот должен отправить: {message}')
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug(f'Бот успешно отправил: {message}')
    except Exception as error:
        logging.error(f'Бот не отправил {message}. Ошибка {error}')


def get_api_answer(current_timestamp):
    """Получение API ответа от эндпоинта."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        error_text = (f'Сбой в работе программы: Эндпоинт {ENDPOINT} '
                      f'недоступен. Код ответа API: {response.status_code}')
        if response.status_code != 200:
            raise requests.exceptions.HTTPError(error_text)
        response = response.json()
        return response
    except requests.exceptions.RequestException as error:
        raise ExceptionError(
            f'Проблема с ответом сервера: {error}',
            response,
            params)


def check_response(response):
    """Проверка ответа API на корректность."""
    if not isinstance(response, dict):
        raise TypeError('Ответ от эндпоинта пришел не в формате словаря')
    if 'homeworks' not in response:
        raise KeyError('Данных homeworks нет в ответе эндпоинта')
    if 'current_date' not in response:
        raise KeyError('Данных current_date нет в ответе эндпоинта')
    if not isinstance(response['current_date'], int):
        raise TypeError('Данные current_date получены не в формате int')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('Данные homeworks получены не в виде списка')
    return homeworks


def parse_status(homework):
    """Проверка статуса работы, полученного в API."""
    if 'homework_name' not in homework:
        raise KeyError('Данных homework_name нет в ответе эндпоинта')
    if 'status' not in homework:
        raise KeyError('Данных status нет в ответе эндпоинта')
    homework_name = homework['homework_name']
    homework_status = homework['status']
    if homework_status not in HOMEWORK_VERDICTS:
        message = f'{homework_status} статус домашней работы не определен!'
        raise KeyError(message)
    verdict = HOMEWORK_VERDICTS.get(homework_status)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка токенов."""
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def main():
    """Основной принцип работы бота."""
    if not check_tokens():
        logging.critical(
            'отсутствие обязательных переменных окружения',
            'во время запуска бота, бот остановлен',
        )
        quit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    send_message(bot, 'Начало работы')
    current_timestamp = int(time.time())
    old_error = ''
    while True:
        try:
            response = get_api_answer(current_timestamp)
            current_timestamp = response.get('current_date')
            logging.debug('Начало проверки ответа сервера')
            homeworks = check_response(response)
            if not homeworks:
                logging.debug('Статус домашней работы не изменился')
            else:
                message = parse_status(homeworks[0])
                send_message(bot, message)
            send_message(bot, 'Пауза')
        except Exception as error:
            logging.error(error)
            if error != old_error:
                message = f'Сбой в работе программы: {error}'
                send_message(bot, message)
                old_error = error
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    format = '%(asctime)s, %(levelname)s, %(message)s'
    logging.basicConfig(
        level=logging.DEBUG,
        filename='my_logger.log',
        format=format,
        filemode='a',
    )
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(format))
    main()
