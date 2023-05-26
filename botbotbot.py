
import time
import base64
import hmac
import hashlib
import requests
import json
import pandas as pd
import talib
import numpy as np
from binance.client import Client
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

class BtcTurkBot:
    def __init__(self, api_key, api_secret, pair_symbol, quantity):
        self.api_key = api_key
        self.api_secret = base64.b64decode(api_secret)
        self.pair_symbol = pair_symbol
        self.quantity = quantity

    def generate_signature(self, data):
        signature = hmac.new(self.api_secret, data.encode('utf-8'), hashlib.sha256).digest()
        signature = base64.b64encode(signature)
        return signature

    def place_sell_order(self):
        base_url = "https://api.btcturk.com"
        endpoint = "/api/v1/order"
        uri = base_url + endpoint

        timestamp = str(int(time.time()) * 1000)
        data = "{}{}".format(self.api_key, timestamp)
        signature = self.generate_signature(data)

        headers = {
            "X-PCK": self.api_key,
            "X-Stamp": timestamp,
            "X-Signature": signature,
            "Content-Type": "application/json"
        }

        params = {
            "quantity": self.quantity,
            "stopPrice": 0,
            "newOrderClientId": "Sell Bot",
            "orderMethod": "market",
            "orderType": "sell",
            "pairSymbol": self.pair_symbol
        }

        response = requests.post(url=uri, headers=headers, json=params)
        result = response.json()

        return result

    def place_buy_order(self):
        base_url = "https://api.btcturk.com"
        endpoint = "/api/v1/order"
        uri = base_url + endpoint

        timestamp = str(int(time.time()) * 1000)
        data = "{}{}".format(self.api_key, timestamp)
        signature = self.generate_signature(data)

        headers = {
            "X-PCK": self.api_key,
            "X-Stamp": timestamp,
            "X-Signature": signature,
            "Content-Type": "application/json"
        }

        params = {
            "quantity": self.quantity,
            "stopPrice": 0,
            "newOrderClientId": "Sell Bot",
            "orderMethod": "market",
            "orderType": "buy",
            "pairSymbol": self.pair_symbol
        }

        response = requests.post(url=uri, headers=headers, json=params)
        result = response.json()

        return result


class Data:
    def __init__(self, interval, symbol, period, telegram, btcturk_bot):
        self.interval = interval
        self.symbol = symbol
        self.period = period
        self.telegram = telegram
        self.btcturk_bot = btcturk_bot

    def fetch_data(self, context: CallbackContext):
        binance_url = 'https://api.binance.com/api/v3/klines'
        params = {
            'symbol': self.symbol.upper(),
            'interval': self.interval
        }
        response = requests.get(binance_url, params=params)
        data = response.json()

        df = pd.DataFrame(data)
        df.columns = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume',
                      'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore']
        df['close'] = pd.to_numeric(df['close'])

        # Calculate RSI
        delta = df['close'].diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        ema_up = up.ewm(com=self.period - 1, adjust=False).mean()
        ema_down = down.ewm(com=self.period - 1, adjust=False).mean()
        rs = ema_up / ema_down
        rsi = 100 - (100 / (1 + rs))

        # Calculate StochRSI 'K' and 'D' lines
        min_rsi = rsi.rolling(window=self.period).min()
        max_rsi = rsi.rolling(window=self.period).max()
        stoch_rsi = 100 * (rsi - min_rsi) / (max_rsi - min_rsi)
        stoch_rsi_k = stoch_rsi.rolling(window=3).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=3).mean()

        # Calculate Parabolic SAR
        high = df['high'].astype(float)
        low = df['low'].astype(float)
        close = df['close'].astype(float)
        sar = talib.SAR(high, low, acceleration=0.02, maximum=0.2)

        context.bot_data['k'] = stoch_rsi_k.iloc[-1]
        context.bot_data['d'] = stoch_rsi_d.iloc[-1]
        context.bot_data['sar'] = sar.iloc[-1]
        context.bot_data['close'] = close.iloc[-1]

        self.analyze_data(context)

    def analyze_data(self, context: CallbackContext):
        k = context.bot_data.get('k')
        d = context.bot_data.get('d')
        sar = context.bot_data.get('sar')
        close = context.bot_data.get('close')

        if k is not None and d is not None and sar is not None and close is not None:
            if k < 20 and d < 20:
                stoch_signal = 'AL'
                result = self.btcturk_bot.place_buy_order()
                print(json.dumps(result, indent=2))
            elif k > 80 and d > 80:
                stoch_signal = 'SAT'
                result = self.btcturk_bot.place_sell_order()
                print(json.dumps(result, indent=2))
            else:
                stoch_signal = 'BEKLE'
            sar_signal = 'AL' if close > sar else 'SAT'

            context.bot.send_message(chat_id=self.telegram.chat_id,
                                     text=f'Son Stokastik RSI K değeri: {k:.2f}, D değeri: {d:.2f}, '
                                          f'Stochastic Signal: {stoch_signal}\n'
                                          f'Parabolic SAR değeri: {sar:.2f}, '
                                          f'SAR Signal: {sar_signal}')


class Telegram:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id

    def run_bot(self, data_instance):
        updater = Updater(token=self.token)
        dispatcher = updater.dispatcher
        dispatcher.add_handler(CommandHandler('start', self.start))
        updater.start_polling()
        job_queue = updater.job_queue
        job_queue.run_repeating(data_instance.fetch_data, interval=60, first=0)
        updater.idle()

    def start(self, update: Update, _: CallbackContext):
        update.message.reply_text('Ben bir Telegram botuyum')


api_key = "BTC_API_KEY"
api_secret = "BTC_SECRET_KEY"
pair_symbol = "COIN"
quantity = 60
btcturk_bot = BtcTurkBot(api_key, api_secret, pair_symbol, quantity)

telegram_token = 'TELEGRAM_TOKEN'
telegram_chat_id = 'TELEGRAM_CHAT_ID'
telegram = Telegram(telegram_token, telegram_chat_id)
data = Data('15m', 'usdttry', 14, telegram, btcturk_bot)
telegram.run_bot(data)
