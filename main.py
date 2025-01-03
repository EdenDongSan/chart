import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
from PyQt6.QtCore import QTimer
import mplfinance as mpf
import pandas as pd
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import mysql.connector
from datetime import datetime, timedelta
import numpy as np
from dotenv import load_dotenv
import os

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
        
        # 캔들 데이터 조회
        cursor.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM kline_1m
            ORDER BY timestamp DESC
            LIMIT %s
        """, (minutes,))
        candles = cursor.fetchall()
        
        # RSI와 롱 비율 데이터 조회
        cursor.execute("""
            SELECT timestamp, oi_rsi, long_ratio
            FROM market_indicators
            ORDER BY timestamp DESC
            LIMIT %s
        """, (minutes,))
        indicators = cursor.fetchall()
        
        # 거래 기록 조회
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
        
        # 타이머 설정 (1초마다 업데이트)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_chart)
        self.timer.start(1000)
        
    def init_ui(self):
        layout = QVBoxLayout()
        self.canvas = FigureCanvas(mpf.figure(figsize=(12, 8)))
        layout.addWidget(self.canvas)
        self.setLayout(layout)
        
    def prepare_data(self, candles, indicators):
        """데이터 전처리"""
        df = pd.DataFrame(candles)
        df.set_index('timestamp', inplace=True)
        df.index = pd.to_datetime(df.index, unit='ms').tz_localize('UTC').tz_convert('Asia/Seoul')  # 시간대 변환
        df = df.sort_index()

        # 지표 데이터 처리
        ind_df = pd.DataFrame(indicators)
        ind_df.set_index('timestamp', inplace=True)
        ind_df.index = pd.to_datetime(ind_df.index, unit='ms').tz_localize('UTC').tz_convert('Asia/Seoul')
        ind_df = ind_df.sort_index()

        # EMA 계산
        df['ema200'] = df['close'].ewm(span=200).mean()

        # Long Ratio를 퍼센트로 변환
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

        # 추가 플롯 설정
        apds = [
            # EMA200
            mpf.make_addplot(df['ema200'], color='blue', width=1),
            # OI RSI
            mpf.make_addplot(ind_df['oi_rsi'], color='purple', width=1),
            # Long Ratio
            mpf.make_addplot(ind_df['long_ratio'], color='green', width=1, ylabel='Long Ratio %', ylim=(60, 90)),
        ]

        # 거래 마커 추가
        if trades:
            for trade in trades:
                trade_time = pd.to_datetime(trade['timestamp'], unit='ms').tz_localize('UTC').tz_convert('Asia/Seoul')
                if trade_time in df.index:  # 차트 범위 내 거래만 표시
                    if trade['side'] == 'long':
                        apds.append(mpf.make_addplot(
                            pd.Series(trade['entry_price'], index=[trade_time]),
                            scatter=True, markersize=100, marker='^', color='g'))
                    else:
                        apds.append(mpf.make_addplot(
                            pd.Series(trade['entry_price'], index=[trade_time]),
                            scatter=True, markersize=100, marker='v', color='r'))

        # 차트 스타일 설정
        style = mpf.make_mpf_style(base_mpf_style='charles', 
                                    gridstyle=':', 
                                    gridcolor='gray',
                                    y_on_right=False)

        # 차트 그리기
        fig, axes = mpf.plot(df, type='candle',
                            addplot=apds,
                            volume=True,
                            style=style,
                            figscale=1.5,
                            panel_ratios=(6, 1),
                            datetime_format='%Y-%m-%d %H:%M',
                            returnfig=True)

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