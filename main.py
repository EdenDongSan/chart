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
        """차트 업데이트"""
        # 데이터 가져오기
        candles, indicators, trades = self.db.get_recent_data()
        df, ind_df = self.prepare_data(candles, indicators)  # 데이터 전처리

        # 최신 데이터로 필터링 (마지막 200개 캔들만 사용)
        df = df.tail(200)
        ind_df = ind_df.tail(200)

        # 캔들 차트 및 거래량 차트를 위한 Figure와 Axes 생성
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})

        # 첫 번째 패널: 캔들 차트
        mpf.plot(
            df,
            type='candle',
            ax=ax1,
            style=mpf.make_mpf_style(base_mpf_style='charles', gridstyle=':', gridcolor='gray')
        )

        # 두 번째 패널: 볼륨 표시
        ax2.bar(df.index, df['volume'], color='gray', width=0.001)
        ax2.set_ylabel('Volume')

        # 첫 번째 오른쪽 Y축: OI RSI
        ax3 = ax1.twinx()
        ax3.plot(ind_df.index, ind_df['oi_rsi'], color='purple', label='OI RSI')
        ax3.set_ylabel('OI RSI', color='purple')
        ax3.tick_params(axis='y', colors='purple')

        # 두 번째 오른쪽 Y축: Long Ratio
        ax4 = ax1.twinx()
        ax4.spines['right'].set_position(('axes', 1.1))
        ax4.plot(ind_df.index, ind_df['long_ratio'], color='green', label='Long Ratio %')
        ax4.set_ylabel('Long Ratio %', color='green')
        ax4.tick_params(axis='y', colors='green')

        # 캔버스 업데이트
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
