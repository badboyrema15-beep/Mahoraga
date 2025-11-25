import ccxt
import pandas as pd
import time
from datetime import datetime
from dash import Dash, dcc, html
from dash.dependencies import Output, Input
import plotly.graph_objs as go
import threading

# ------------------------
# CONFIG
# ------------------------
API_KEY = "3l7wax0Lw1Dj0ueE62BzYyFhuLrAfPdHIV3EiiKPxDURqJiJp5rCWnqdwrsVmA64"
API_SECRET = "C6RWSuWh57HFjHOJ5VAZIWhqwNvjoEV7YZQCpsWmQlHgDKRosaptIOkEm4VEGK3Lgi"
PAIRS = ["BTC/USDT", "ETH/USDT", "SHIB/USDT", "ADA/USDT", "SOL/USDT"]
TIMEFRAME = '1m'
LIMIT = 100
INITIAL_BALANCE = 50
MAX_RISK = 0.2
ATR_PERIOD = 14

# ------------------------
# CONNECT TO BINANCE TESTNET
# ------------------------
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
})
exchange.set_sandbox_mode(True)

# ------------------------
# BALANCE & POSITIONS
# ------------------------
balance = {pair: INITIAL_BALANCE for pair in PAIRS}
open_positions = {pair: None for pair in PAIRS}
trade_logs = {pair: [] for pair in PAIRS}

# ------------------------
# FETCH DATA
# ------------------------
def fetch_data(pair):
    ohlcv = exchange.fetch_ohlcv(pair, timeframe=TIMEFRAME, limit=LIMIT)
    df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['H-L'] = df['high'] - df['low']
    df['ATR'] = df['H-L'].rolling(ATR_PERIOD).mean()
    return df

# ------------------------
# BOX STRATEGY LOGIC
# ------------------------
min_box = {
    "BTC/USDT": 50,
    "ETH/USDT": 5,
    "SHIB/USDT": 0.0000005,
    "ADA/USDT": 0.01,
    "SOL/USDT": 0.5
}

def check_trade_signal(pair, df):
    last_close = df['close'].iloc[-1]
    atr = df['ATR'].iloc[-1]
    box_size = max(atr, min_box[pair])
    if open_positions[pair] is None and last_close <= df['close'].min() + box_size:
        return "BUY", box_size
    elif open_positions[pair] is not None and last_close >= open_positions[pair]['entry'] + box_size:
        return "SELL", box_size
    else:
        return None, box_size

# ------------------------
# EXECUTE TRADE
# ------------------------
def execute_trade(pair, signal, box_size):
    global balance, open_positions, trade_logs
    last_close = fetch_data(pair)['close'].iloc[-1]
    if signal == "BUY" and open_positions[pair] is None:
        trade_size = balance[pair] * MAX_RISK
        open_positions[pair] = {"type":"LONG","entry":last_close,"size":trade_size,"box_size":box_size}
        trade_logs[pair].append({"type":"BUY","price":last_close,"size":trade_size,"time":datetime.now().isoformat()})
    elif signal == "SELL" and open_positions[pair] is not None:
        pnl = (last_close - open_positions[pair]['entry']) / open_positions[pair]['entry'] * open_positions[pair]['size']
        balance[pair] += pnl
        trade_logs[pair].append({"type":"SELL","price":last_close,"pnl":pnl,"balance":balance[pair],"time":datetime.now().isoformat()})
        open_positions[pair] = None

# ------------------------
# BOT THREAD
# ------------------------
def run_bot():
    while True:
        for pair in PAIRS:
            df = fetch_data(pair)
            signal, box_size = check_trade_signal(pair, df)
            if signal:
                execute_trade(pair, signal, box_size)
        time.sleep(10)

bot_thread = threading.Thread(target=run_bot)
bot_thread.start()

# ------------------------
# DASHBOARD
# ------------------------
app = Dash(__name__)

app.layout = html.Div([
    html.H1("Mahoraga Live Dashboard"),
    dcc.Interval(id='interval', interval=10*1000, n_intervals=0),
    html.Div(id='balances'),
    html.Div(id='charts')
])

@app.callback(
    Output('balances', 'children'),
    Output('charts', 'children'),
    Input('interval', 'n_intervals')
)
def update_dashboard(n):
    balances_text = [html.H3(f"{pair} Balance: {balance[pair]:.2f}") for pair in PAIRS]
    charts_divs = []
    for pair in PAIRS:
        df = fetch_data(pair)
        last_box = max(df['ATR'].iloc[-1], min_box[pair])
        trace = go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])
        layout = go.Layout(title=f"{pair} Price & Box", shapes=[
            dict(type="line", x0=df['timestamp'].iloc[0], x1=df['timestamp'].iloc[-1], y0=df['close'].min()+last_box, y1=df['close'].min()+last_box,
                 line=dict(color="green", dash="dash")),
            dict(type="line", x0=df['timestamp'].iloc[0], x1=df['timestamp'].iloc[-1], y0=df['close'].min(), y1=df['close'].min(),
                 line=dict(color="red", dash="dash"))
        ])
        fig = go.Figure(data=[trace], layout=layout)
        charts_divs.append(dcc.Graph(figure=fig))
    return balances_text, charts_divs

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=8050)
