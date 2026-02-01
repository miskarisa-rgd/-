import telebot

bot = telebot.TeleBot('8248272716:AAGgypGFGkmjgaOFjSaLRmXSJ8yLBFgMAU0')

@bot.message_handler(commands=['start']) #если добавить сюда через запятую  допустим 'main' то на /main бот тоже будет откликаться.
def main(message):
    bot.send_message(message.chat.id, 'hello!')

bot.polling(none_stop = True)