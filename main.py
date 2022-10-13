import functools
import time

from settings import TOKEN  # Здесь надо импортировать токен бота
from telegram import Update
from telegram.ext import Updater, CallbackContext, CommandHandler, MessageHandler, Filters, JobQueue
from apscheduler.schedulers.background import BackgroundScheduler
from log import get_logger

scheduler = BackgroundScheduler()
logger = get_logger(__name__)  # TODO переделать file_handler, обновление по месяцам


def log_action(command):
    """
    Декоратор, который логирует все действия бота и возникающие ошибки
    """

    @functools.wraps(command)
    def wrapper(*args, **kwargs):
        try:
            if len(args) == 1:
                logger.info(f'Cработала функция {command.__name__}')
            else:
                update = args[0]
                username = update.message.from_user.username
                logger.info(f'{username} вызвал функцию {command.__name__}')
            return command(*args, **kwargs)
        except:
            logger.exception(f'Ошибка в обработчике {command.__name__}')
            raise

    return wrapper


def main() -> None:
    """
    Создает и запускает бота для Актового зала
    Команды, которые понимает бот:
        /takekey - записать ключ на пользователя
        /passkey - сдать ключ на вахту
        /wherekey - рассказать, у кого ключ в данный момент
        /gethistory - в разработке
    """
    updater = Updater(token=TOKEN)
    dispatcher = updater.dispatcher
    job_queue: JobQueue = updater.job_queue
    job_queue.set_dispatcher(dispatcher)

    # Добавляем обработчики команд
    dispatcher.add_handler(CommandHandler('takekey', take_key))
    dispatcher.add_handler(CommandHandler('passkey', pass_key))
    dispatcher.add_handler(CommandHandler('wherekey', where_key))
    dispatcher.add_handler(CommandHandler('gethistory', get_history))
    dispatcher.add_handler(CommandHandler('showevent', show_event))


    # На любой другой текст выдаем сообщение help
    dispatcher.add_handler(MessageHandler(Filters.text, do_help))

    # Запускаем бота
    updater.start_polling()
    logger.info('auditory_bot успешно запустился')
    updater.idle()  # Это нужно, чтобы сразу не завершился


@log_action
def take_key(update: Update, context: CallbackContext) -> None:
    """Записывает в контекст беседы пользователя, который взял ключ, и пишет об этом в чат
    :param update: обновление из Telegram, новое для каждого сообщения
    :param context: контекст беседы, из которой прилетело сообщение. Не меняется при новом сообщении
    :return: None
    """
    user = update.message.from_user
    if 'key_taken' not in context.chat_data:
        context.chat_data['key_taken'] = False
    if context.chat_data['key_taken']:  # TODO учесть случай, когда ключ передает сам себе
        reply = f'Ключ передал {context.chat_data["user"]}'
        logger.debug(reply)
        update.message.reply_text(text=reply)
    context.chat_data['key_taken'] = True
    context.chat_data['user_id'] = user.id
    context.chat_data['user'] = f'{user.first_name} {user.last_name}'
    # TODO Вынести получение имени и фамилии в отдельную функцию. Нужен фильтр, если фамилия None
    reply = f'Ключ взял {user.first_name} {user.last_name}'
    logger.debug(reply)
    update.message.reply_text(text=reply)
    context.job_queue.run_repeating(callback_minute, interval=20, first=10, context=context)


@log_action
def pass_key(update: Update, context: CallbackContext) -> None:
    """Пишет в чат о том, кто пользователь сдал ключ, и стирает запись о взятом ключе из контекста беседы
    :param update: обновление из Telegram, новое для каждого сообщения
    :param context: контекст беседы, из которой прилетело сообщение. Не меняется при новом сообщении
    :return: None
    """
    user = update.message.from_user
    # TODO учесть случай, когда ключа ни у кого нет
    context.chat_data.clear()
    context.chat_data['key_taken'] = False
    # TODO учесть случай, когда сдает не тот, кто взял

    reply = f'Ключ сдал {user.first_name} {user.last_name}'
    logger.debug(reply)
    update.message.reply_text(text=reply)


@log_action
def where_key(update: Update, context: CallbackContext) -> None:
    """Пишет в чат, у кого ключ, исходя из информации, записанной в контексте беседы:
        Либо ключ у пользователя (context.chat_data['user'])
        Либо ключ на вахте (флаг context.chat_data['key_taken'])
    :param update: обновление из Telegram, новое для каждого сообщения
    :param context: контекст беседы, из которой прилетело сообщение. Не меняется при новом сообщении
    :return: None
    """
    if context.chat_data['key_taken']:
        user = update.message.from_user
        reply = f'Ключ взял {user.first_name} {user.last_name}'
        logger.debug(reply)
        update.message.reply_text(text=reply)
    else:
        reply = f'Ключ на вахте'
        logger.debug(reply)
        update.message.reply_text(text=reply)


@log_action
def get_history(update: Update, context: CallbackContext) -> None:
    """Возвращает в чат историю путешествия ключа по рукам
    :param update: обновление из Telegram, новое для каждого сообщения
    :param context: контекст беседы, из которой прилетело сообщение. Не меняется при новом сообщении
    :return: None
    """
    update.message.reply_text(text='С этим пока трудности, работаем...')


@log_action
def do_help(update: Update, context: CallbackContext) -> None:
    """Пишет в чат команды, которые понимает бот
    :param update: обновление из Telegram, новое для каждого сообщения
    :param context: контекст беседы, из которой прилетело сообщение. Не меняется при новом сообщении
    :return: None
    """
    user = update.message.from_user
    update.message.reply_text(
        text=f'Привет, {user.first_name} {user.last_name}!\n\n'
             f'Вот команды, которые я понимаю:\n'
             f'/takekey - я запишу ключ на твое имя\n'
             f'/passkey - я запишу, что ты сдал ключ на вахту\n'
             f'/wherekey - я расскажу, у кого ключ\n'
             f'/gethistory - я расскажу, кто последний брал ключ\n'
             f'/gethistory - я расскажу, кто последний брал ключ\n'
             f'/showevent - я расскажу, какие события намечаются\n'
    )


def two_hour_remind(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    reply = f'Эй, {user.first_name} {user.last_name}, не забыл сдать ключ?'
    time.sleep(8)  # Это чтобы не напоминал сдать ключ сразу после команды "takekey"
    if context.chat_data['key_taken'] == True:
        update.message.reply_text(reply)
        time.sleep(8)


@log_action
def show_event(update: Update, context: CallbackContext) -> None:
    # TODO команда вызова календаря
    pass


@log_action
def callback_minute(context: CallbackContext):
    context.bot.send_message(chat_id=1627741936,
                             text=context.job)

    if context.chat_data['key_taken']:
        context.bot.send_message(chat_id=1627741936,
                                 text='One message every minute')


if __name__ == '__main__':
    main()

