import functools, json

from settings import TOKEN  # Здесь надо импортировать токен бота
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CallbackContext, CommandHandler, MessageHandler, Filters, JobQueue, CallbackQueryHandler
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
        /help - написать, что умеет бот
        /takekey - записать ключ на пользователя
        /passkey - сдать ключ на вахту
        /wherekey - рассказать, у кого ключ в данный момент
        /gethistory - в разработке
        /fix - записать в список то, что лучше не трогать
        /isfixed - написать список в чат
        /unfix - удалить что-то из списка
    """

    global flag, name, items_is_not_empty
    items_is_not_empty = 0
    flag = 0
    name = ''

    updater = Updater(token=TOKEN)
    dispatcher = updater.dispatcher
    job_queue = JobQueue()
    job_queue.set_dispatcher(dispatcher)

    # Добавляем обработчики команд
    dispatcher.add_handler(CommandHandler('takekey', take_key))
    dispatcher.add_handler(CommandHandler('passkey', pass_key))
    dispatcher.add_handler(CommandHandler('wherekey', where_key))
    dispatcher.add_handler(CommandHandler('gethistory', get_history))
    dispatcher.add_handler(CommandHandler('help', do_help))
    dispatcher.add_handler(CommandHandler('fix', fix))
    dispatcher.add_handler(CommandHandler('isfixed', isfix))
    dispatcher.add_handler(CommandHandler('unfix', unfix))
    dispatcher.add_handler(MessageHandler(Filters.update, waiting_func))
    dispatcher.add_handler(CallbackQueryHandler(button))

    # На любой другой текст выдаем сообщение help
    dispatcher.add_handler(MessageHandler(Filters.text, do_help))

    # Запускаем бота
    updater.start_polling()
    job_queue.start()
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
        remove_job_if_exists(context)
    context.chat_data['key_taken'] = True
    context.chat_data['user_id'] = user.id
    context.chat_data['user'] = f'{user.first_name} {user.last_name}'
    # TODO Вынести получение имени и фамилии в отдельную функцию. Нужен фильтр, если фамилия None

    # Если fixed_items.json не пустой, отправляем в чат содержимое
    itms = get_fixed()

    flight = itms[0]
    fscenes = itms[1]

    if len(flight) > 0 or len(fscenes) > 0:
        global items_is_not_empty
        items_is_not_empty = 1
        isfix(update, context)

    reply = f'Ключ взял {user.first_name} {user.last_name}'
    logger.debug(reply)
    update.message.reply_text(text=reply)
    context.job_queue.run_repeating(callback_minute, 3600, first=1800, context=update.message.chat_id)
    global name
    name = str(user.first_name) + ' ' + str(user.last_name)


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
    remove_job_if_exists(context)


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
        reply = f"Ключ взял {context.chat_data['user']}"
        logger.debug(reply)
        update.message.reply_text(text=reply)
    else:
        reply = f"Ключ на вахте"
        logger.debug(reply)
        update.message.reply_text(text=reply)


@log_action
def get_history(update: Update, context: CallbackContext) -> None:
    """Возвращает в чат историю путешествия ключа по рукам.
    :param update: обновление из Telegram, новое для каждого сообщения.
    :param context: контекст беседы, из которой прилетело сообщение. Не меняется при новом сообщении.
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
             f'/fix - я запишу в список то, что лучше не трогать\n'
             f'/unfix - я удалю что-то из этого списка\n'
             f'/isfixed - я прочитаю список\n'

    )


@log_action
def fix(update, context: CallbackContext):
    button_list = [
        InlineKeyboardButton("Сцены", callback_data="СЦЕНЫ"),
        InlineKeyboardButton("Прожектора", callback_data="ПРОЖЕКТОРА"),
    ]
    reply_markup = InlineKeyboardMarkup(build_menu(button_list, n_cols=2))
    context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите:", reply_markup=reply_markup)


def isfix(update, context: CallbackContext):
    global items_is_not_empty

    if  items_is_not_empty == 1:
        itms = get_fixed()

        update.message.reply_text(
            text=f'Попросили кое-что не трогать!\n'
                 f'Прожектора:\n'
                 f"{' '.join(itms[0])}\n"
                 f'Сцены:\n'
                 f"{' '.join(itms[1])}\n"
        )
        items_is_not_empty = 0

    else:
        itms = get_fixed()

        update.message.reply_text(
            text=f'Прожектора:\n'
                f"{' '.join(itms[0])}\n"
                f'Сцены:\n'
                f"{' '.join(itms[1])}\n"
            )


def unfix(update, context: CallbackContext):
    global flag
    flag = 1
    fix(update, context)


@log_action
def callback_minute(context: CallbackContext):
    global name
    context.bot.send_message(chat_id=context.job.context,
                             text= f"{name}, не забудь сдать ключ на вахту!")


def remove_job_if_exists(context):
    """
       Удаляет задание с заданным именем.
       Возвращает, было ли задание удалено
    """
    current_jobs = context.job_queue.jobs()

    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


@log_action
def build_menu(buttons, n_cols,
               header_buttons=None,
               footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, [header_buttons])
    if footer_buttons:
        menu.append([footer_buttons])
    return menu


def button(update, context: CallbackContext):
    # TODO стирать сообщения, чтобы не засорять чат
    query = update.callback_query
    variant = query.data
    query.answer()

    if variant == "ПРОЖЕКТОРА":
        context.bot.send_message(chat_id=update.effective_chat.id, text="Введите номера прожекторов через пробел: ")
        context.chat_data['waiting for'] = 'light'

    elif variant == "СЦЕНЫ":
        context.bot.send_message(chat_id=update.effective_chat.id, text="Введите номера сцен через пробел: ")
        context.chat_data['waiting for'] = 'scenes'
        change_scenes(update, context)


def waiting_func(update, context):
    if context.chat_data.get('waiting for') == 'light':
        change_light(update, context)
    if context.chat_data.get('waiting for') == 'scenes':
        change_scenes(update, context)


def change_light(update, context: CallbackContext):
    global flag

    if flag == 1:  # пользователь хочет удалить значение

        delete_from_fixed(update.message.text.split(), 0)  # если 0 - то меняется свет
        flag = 0
        context.chat_data['waiting for'] = ''

    else:  # пользователь хочет добавить значение
        write_in_fixed(update.message.text.split(), 0) # если 0 - то меняется свет
        context.chat_data['waiting for'] = ''



    update.message.reply_text(
        text=f'Принято!\n\n'
             f'Я напомню про это по команде:\n'
             f'/isfixed\n'
             f'И изменю список по команде:\n'
             f'/unfix\n'

    )


def change_scenes(update, context: CallbackContext):
    global flag

    if flag == 1:  # пользователь хочет удалить значение

        delete_from_fixed(update.message.text.split(), 1)   # если 1 - то меняются сцены
        flag = 0
        context.chat_data['waiting for'] = ''

    else:  # пользователь хочет добавить значение
        write_in_fixed(update.message.text.split(), 1)  # если 1 - то меняются сцены
        context.chat_data['waiting for'] = ''

    update.message.reply_text(
        text=f'Принято!\n\n'
             f'Я напомню про это по команде:\n'
             f'/isfixed\n'
             f'И уберу что-то из списка по команде:\n'
             f'/unfix\n'

    )


def write_in_fixed(s, type):
    print('write in fixed')

    itms = get_fixed()

    flight = itms[0]
    fscenes = itms[1]

    result = {'light': flight, 'scenes': fscenes}

    if type == 0:    # если 0 - то меняется свет
        result["light"] += s
    if type == 1:   # если 1 - то меняются сцены
        result["scenes"] += s

    with open('fixed_items.json', 'w') as f:
        json.dump(result, f)


def delete_from_fixed(s, type):

    itms = get_fixed()

    flight = itms[0]
    fscenes = itms[1]

    if type == 0:    # если 0 - то меняется свет
        for i in range(len(s)):
            z = s[i]
            flight.remove(z)

    if type == 1:   # если 1 - то меняются сцены
        for i in range(len(s)):
            z = s[i]
            fscenes.remove(z)

    result = {'light': flight, 'scenes': fscenes}

    with open('fixed_items.json', 'w') as f:
        json.dump(result, f)
    pass


def get_fixed():
    with open('fixed_items.json') as f:
        fixed = json.load(f)
        return fixed["light"], fixed["scenes"]


if __name__ == '__main__':
    main()

