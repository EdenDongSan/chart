import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
from PyQt6.QtCore import QTimer
import mplfinance as mpf
import pandas as pd
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import mysql.connector
from datetime import datetime
import numpy as np
from dotenv import load_dotenv
import os
import matplotlib.pyplot as plt

# .env 파일 로드
load_dotenv()

class DatabaseManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.db = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DATABASE')
        )

    def get_recent_data(self, minutes=200):
        """최근 데이터 조회"""
        cursor = self.db.cursor(dictionary=True)
        cursor.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM kline_1m
            ORDER BY timestamp DESC
            LIMIT %s
        """, (minutes,))
        candles = cursor.fetchall()

        cursor.execute("""
            SELECT timestamp, oi_rsi, long_ratio
            FROM market_indicators
            ORDER BY timestamp DESC
            LIMIT %s
        """, (minutes,))
        indicators = cursor.fetchall()

        cursor.execute("""
            SELECT timestamp, side, entry_price, exit_price, size
            FROM trade_history
            WHERE timestamp >= %s
        """, (candles[-1]['timestamp'],))
        trades = cursor.fetchall()

        cursor.close()
        return candles, indicators, trades


class TradingChart(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.init_ui()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_chart)
        self.timer.start(1000)

    def init_ui(self):
        layout = QVBoxLayout()
        self.canvas = FigureCanvas(plt.figure(figsize=(12, 8)))
        layout.addWidget(self.canvas)
        self.setLayout(layout)

    def prepare_data(self, candles, indicators):
        df = pd.DataFrame(candles)
        df.set_index('timestamp', inplace=True)
        df.index = pd.to_datetime(df.index, unit='ms').tz_localize('UTC').tz_convert('Asia/Seoul')
        df = df.sort_index()

        ind_df = pd.DataFrame(indicators)
        ind_df.set_index('timestamp', inplace=True)
        ind_df.index = pd.to_datetime(ind_df.index, unit='ms').tz_localize('UTC').tz_convert('Asia/Seoul')
        ind_df = ind_df.sort_index()

        df['ema200'] = df['close'].ewm(span=200).mean()
        ind_df['long_ratio'] = ind_df['long_ratio'] * 100

        return df, ind_df

    def update_chart(self):
        candles, indicators, trades = self.db.get_recent_data()
        df, ind_df = self.prepare_data(candles, indicators)
        df = df.tail(200)
        ind_df = ind_df.tail(200)

        apds = [
            mpf.make_addplot(df['ema200'], color='blue', width=1)
        ]

        fig, ax1 = plt.subplots(figsize=(12, 8))
        mpf.plot(df, type='candle', ax=ax1, volume=True)

        ax2 = ax1.twinx()
        ax2.plot(ind_df.index, ind_df['oi_rsi'], color='purple', label='OI RSI')
        ax2.set_ylabel('OI RSI', color='purple')
        ax2.tick_params(axis='y', colors='purple')

        ax3 = ax1.twinx()
        ax3.spines['right'].set_position(('axes', 1.1))
        ax3.plot(ind_df.index, ind_df['long_ratio'], color='green', label='Long Ratio %')
        ax3.set_ylabel('Long Ratio %', color='green')
        ax3.tick_params(axis='y', colors='green')

        self.canvas.figure = fig
        self.canvas.draw()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Trading Monitor')
        self.setGeometry(100, 100, 1200, 800)

        chart = TradingChart()
        self.setCentralWidget(chart)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
