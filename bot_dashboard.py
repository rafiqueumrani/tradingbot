import pandas as pd
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn, os, json
from datetime import datetime
from typing import Optional
import requests

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

CSV_FILE = "trades.csv"
STATE_FILE = "state.json"

def safe_read_csv():
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame()
    try:
        return pd.read_csv(CSV_FILE, dtype=str)
    except:
        return pd.DataFrame()

def to_float_clean(s):
    """Safe float conversion with error handling"""
    try:
        if s is None: return None
        if isinstance(s, (int, float)):
            return float(s)
        x = str(s).replace("USDT","").replace("+","").replace(",","").strip()
        if x=="" or x.lower() in ("nan","none", "null"): return None
        return float(x)
    except:
        return None

def safe_float_convert(value, default=0.0):
    """Safely convert any value to float"""
    try:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).strip())
    except (ValueError, TypeError):
        return default

def load_trades():
    df = safe_read_csv()
    expected = ["Trade #","Symbol","Side","Type","Date/Time","Signal","Price","Position size","Net P&L","Run-up","Drawdown","Cumulative P&L"]
    for c in expected:
        if c not in df.columns:
            df[c] = ""
    df = df.fillna("")
    try:
        df["__dt_parsed"] = pd.to_datetime(df["Date/Time"], format='%b %d, %Y, %H:%M', errors="coerce")
    except:
        df["__dt_parsed"] = pd.to_datetime(df["Date/Time"], errors="coerce")
    df["NetPnl_num"] = df["Net P&L"].apply(lambda v: to_float_clean(v) if v else 0.0)
    
    if not df.empty and "Trade #" in df.columns:
        df["Trade_Num"] = pd.to_numeric(df["Trade #"], errors="coerce")
        df = df.sort_values("Trade_Num", ascending=False)
    return df

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE,"r") as f:
            return json.load(f)
    except:
        return {}

def save_state(st):
    try:
        with open(STATE_FILE,"w") as f:
            json.dump(st,f,indent=2)
        return True
    except:
        return False

def get_current_price(symbol):
    """Get current price from Binance API"""
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return float(data['price'])
    except:
        pass
    return None

def calculate_daily_pnl(df):
    if df.empty or "NetPnl_num" not in df.columns:
        return []
    exits = df[df["NetPnl_num"].notnull()].copy()
    if exits.empty:
        return []
    exits["date"] = exits["__dt_parsed"].dt.date
    daily = exits.groupby("date")["NetPnl_num"].sum().reset_index().sort_values("date", ascending=False)
    daily.columns = ["Date","Profit"]
    return daily.to_dict(orient="records")

def compute_cumulative(df):
    if df.empty:
        return df
    d = df.copy().sort_values("Trade_Num", ascending=True)
    cum = 0.0; computed=[]
    for _, r in d.iterrows():
        pnl = r.get("NetPnl_num")
        if pd.notna(pnl):
            cum += float(pnl)
            computed.append(cum)
        else:
            computed.append(None)
    d["Computed_Cum"] = computed
    def display(row):
        if pd.notna(row["Computed_Cum"]):
            return f"{row['Computed_Cum']:.2f}"
        return row.get("Cumulative P&L","") or ""
    d["Cumulative P&L"] = d.apply(display, axis=1)
    return d

def calculate_risk_metrics(df):
    """Calculate advanced risk metrics"""
    if df.empty:
        return {}
    
    exit_trades = df[df["Signal"].str.contains("Exit|Close", na=False)]
    total_trades = len(exit_trades)
    winning_trades = len(exit_trades[exit_trades["NetPnl_num"] > 0])
    losing_trades = len(exit_trades[exit_trades["NetPnl_num"] < 0])
    breakeven_trades = len(exit_trades[exit_trades["NetPnl_num"] == 0])
    
    total_profit = exit_trades[exit_trades["NetPnl_num"] > 0]["NetPnl_num"].sum()
    total_loss = abs(exit_trades[exit_trades["NetPnl_num"] < 0]["NetPnl_num"].sum())
    
    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "breakeven_trades": breakeven_trades,
        "win_rate": (winning_trades / total_trades * 100) if total_trades > 0 else 0,
        "loss_rate": (losing_trades / total_trades * 100) if total_trades > 0 else 0,
        "profit_factor": (total_profit / total_loss) if total_loss > 0 else float('inf'),
        "largest_win": exit_trades["NetPnl_num"].max() if not exit_trades.empty else 0,
        "largest_loss": exit_trades["NetPnl_num"].min() if not exit_trades.empty else 0,
        "avg_win": exit_trades[exit_trades["NetPnl_num"] > 0]["NetPnl_num"].mean() if winning_trades > 0 else 0,
        "avg_loss": exit_trades[exit_trades["NetPnl_num"] < 0]["NetPnl_num"].mean() if losing_trades > 0 else 0,
    }

def get_open_trades_with_pnl():
    """Get open trades with live PnL calculation"""
    state = load_state()
    open_trades = state.get("open_trades", {})
    
    result = []
    for symbol, trade_info in open_trades.items():
        try:
            entry_price = safe_float_convert(trade_info.get("entry_price"), 0)
            quantity = safe_float_convert(trade_info.get("total_quantity") or trade_info.get("quantity"), 0)
            side = trade_info.get("side", "long")
            
            current_price = get_current_price(symbol)
            if current_price is None:
                current_price = entry_price
            
            if side == "long":
                unrealized_pnl = (current_price - entry_price) * quantity
                pnl_percent = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
            else:
                unrealized_pnl = (entry_price - current_price) * quantity
                pnl_percent = ((entry_price - current_price) / entry_price) * 100 if entry_price > 0 else 0
            
            tp1 = safe_float_convert(trade_info.get("tp1", 0))
            tp2 = safe_float_convert(trade_info.get("tp2", 0))
            tp3 = safe_float_convert(trade_info.get("tp3", 0))
            sl = safe_float_convert(trade_info.get("sl", 0))
            
            tp_targets = trade_info.get("tp_targets", {})
            if tp_targets and tp_targets.get("tp1", {}).get("hit", False):
                sl_display = entry_price
            else:
                sl_display = sl
            
            result.append({
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "current_price": current_price,
                "quantity": quantity,
                "trade_num": trade_info.get("trade_num", 0),
                "pnl": round(unrealized_pnl, 2),
                "pnl_percent": round(pnl_percent, 2),
                "entry_time": trade_info.get("entry_time", ""),
                "sl": sl_display,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "trailing_active": trade_info.get("trailing_active", False),
                "tp_targets": trade_info.get("tp_targets", {}),
                "remaining_quantity": safe_float_convert(trade_info.get("remaining_quantity", 0))
            })
        except Exception as e:
            print(f"Error processing trade {symbol}: {e}")
            continue
    
    return result

def append_trade_row(row: dict):
    """Append a trade row to CSV"""
    try:
        df = safe_read_csv()
        cols = ["Trade #","Symbol","Side","Type","Date/Time","Signal","Price","Position size","Net P&L","Run-up","Drawdown","Cumulative P&L"]
        
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        
        new_row = {c: row.get(c, "") for c in cols}
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(CSV_FILE, index=False, columns=cols)
        return True
    except Exception as e:
        print(f"Error appending trade row: {e}")
        return False

def format_trade_history(df):
    """Format trade history with merged rows for same trade"""
    if df.empty:
        return "<div class='section trade-history-section'><h3>📋 Trade History</h3><p>No trade history available</p></div>"
    
    df_disp = df.sort_values(["Trade_Num", "Date/Time"], ascending=[False, True])
    
    html = """
    <div class="section trade-history-section">
        <h3>📋 Trade History</h3>
        <div class="trade-history-container">
            <table class="trade-table" id="tradesTable">
                <thead>
                    <tr>
                        <th class="col-trade-no">Trade #</th>
                        <th class="col-symbol">Symbol</th>
                        <th class="col-type">Type</th>
                        <th class="col-date">Date / Time</th>
                        <th class="col-signal">Signal</th>
                        <th class="col-price">Price</th>
                        <th class="col-size">Position size</th>
                        <th class="col-pnl">Net P&L</th>
                        <th class="col-runup">Run-up</th>
                        <th class="col-drawdown">Drawdown</th>
                        <th class="col-cumulative">Cumulative P&L</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    current_trade_num = None
    trade_rows = []
    
    for _, row in df_disp.iterrows():
        trade_num = row.get('Trade #', '')
        trade_type = row.get('Type', '')
        date_time = row.get('Date/Time', '')
        signal = row.get('Signal', '')
        price = row.get('Price', '')
        position_size = row.get('Position size', '')
        net_pnl = row.get('Net P&L', '')
        run_up = row.get('Run-up', '')
        drawdown = row.get('Drawdown', '')
        cumulative = row.get('Cumulative P&L', '')
        
        symbol_parts = str(trade_type).split(' ')
        symbol = symbol_parts[0] if symbol_parts else ''
        direction = symbol_parts[1] if len(symbol_parts) > 1 else ''
        
        is_exit = "Exit" in str(signal) or "Close" in str(signal)
        display_type = "Exit" if is_exit else "Entry"
        
        pnl_num = row.get("NetPnl_num", 0)
        pnl_cls = "positive" if pnl_num >= 0 else "negative"
        
        def clean_value(val):
            if not val or pd.isna(val):
                return ""
            return str(val).replace('USD', '').replace('↑', '').replace('+', '').replace(',', '').strip()
        
        def format_currency(val, is_exit=False):
            try:
                clean_val = clean_value(val)
                if clean_val and clean_val != 'nan':
                    return f"{float(clean_val):.2f} USD↑"
            except:
                pass
            return str(val) if val else ""
        
        def format_percentage(val):
            try:
                clean_val = clean_value(val)
                if clean_val and clean_val != 'nan':
                    return f"{float(clean_val):.2f}%"
            except:
                pass
            return str(val) if val else ""
        
        def format_position_size(val, is_exit=False):
            try:
                clean_val = clean_value(val)
                if clean_val and clean_val != 'nan':
                    if is_exit:
                        return f"{float(clean_val):.2f}"
                    else:
                        return f"{float(clean_val):.2f} USD↑"
            except:
                pass
            return str(val) if val else ""
        
        def format_pnl(val, is_exit=False):
            try:
                clean_val = clean_value(val)
                if clean_val and clean_val != 'nan':
                    val_float = float(clean_val)
                    if is_exit:
                        sign = "+" if val_float >= 0 else ""
                        return f"{sign}{val_float:.2f} USD↑"
                    else:
                        sign = "+" if val_float >= 0 else ""
                        return f"{sign}{abs(val_float):.2f}%"
            except:
                pass
            return str(val) if val else ""
        
        formatted_price = format_currency(price, is_exit)
        formatted_position_size = format_position_size(position_size, is_exit)
        formatted_pnl = format_pnl(net_pnl, is_exit)
        formatted_runup = format_percentage(run_up) if not is_exit else format_currency(run_up, is_exit)
        formatted_drawdown = format_percentage(drawdown) if not is_exit else format_currency(drawdown, is_exit)
        formatted_cumulative = format_percentage(cumulative) if not is_exit else format_currency(cumulative, is_exit)
        
        if trade_num != current_trade_num:
            if trade_rows:
                html += process_trade_group(trade_rows)
            trade_rows = []
            current_trade_num = trade_num
        
        trade_rows.append({
            'trade_num': trade_num,
            'symbol': symbol,
            'direction': direction,
            'display_type': display_type,
            'date_time': date_time,
            'signal': signal,
            'formatted_price': formatted_price,
            'formatted_position_size': formatted_position_size,
            'formatted_pnl': formatted_pnl,
            'formatted_runup': formatted_runup,
            'formatted_drawdown': formatted_drawdown,
            'formatted_cumulative': formatted_cumulative,
            'pnl_cls': pnl_cls,
            'is_exit': is_exit
        })
    
    if trade_rows:
        html += process_trade_group(trade_rows)
    
    html += """
                </tbody>
            </table>
        </div>
    </div>
    """
    return html

def process_trade_group(trade_rows):
    """Process a group of trades with same trade number"""
    if not trade_rows:
        return ""
    
    trade_rows.sort(key=lambda x: 0 if x['display_type'] == 'Entry' else 1)
    
    html = ""
    first_row = True
    
    for trade in trade_rows:
        if first_row:
            html += f"""
                    <tr class="trade-row {'exit-row' if trade['is_exit'] else 'entry-row'} {trade['direction'].lower()}">
                        <td class="col-trade-no" rowspan="{len(trade_rows)}">{trade['trade_num']}</td>
                        <td class="col-symbol" rowspan="{len(trade_rows)}">{trade['symbol']} {trade['direction']}</td>
                        <td class="col-type">{trade['display_type']}</td>
                        <td class="col-date">{trade['date_time']}</td>
                        <td class="col-signal">{trade['signal']}</td>
                        <td class="col-price">{trade['formatted_price']}</td>
                        <td class="col-size">{trade['formatted_position_size']}</td>
                        <td class="col-pnl {trade['pnl_cls']}">{trade['formatted_pnl']}</td>
                        <td class="col-runup">{trade['formatted_runup']}</td>
                        <td class="col-drawdown">{trade['formatted_drawdown']}</td>
                        <td class="col-cumulative">{trade['formatted_cumulative']}</td>
                    </tr>
            """
            first_row = False
        else:
            html += f"""
                    <tr class="trade-row {'exit-row' if trade['is_exit'] else 'entry-row'} {trade['direction'].lower()}">
                        <td class="col-type">{trade['display_type']}</td>
                        <td class="col-date">{trade['date_time']}</td>
                        <td class="col-signal">{trade['signal']}</td>
                        <td class="col-price">{trade['formatted_price']}</td>
                        <td class="col-size">{trade['formatted_position_size']}</td>
                        <td class="col-pnl {trade['pnl_cls']}">{trade['formatted_pnl']}</td>
                        <td class="col-runup">{trade['formatted_runup']}</td>
                        <td class="col-drawdown">{trade['formatted_drawdown']}</td>
                        <td class="col-cumulative">{trade['formatted_cumulative']}</td>
                    </tr>
            """
    
    return html

@app.get("/", response_class=HTMLResponse)
def dashboard():
    df = load_trades()
    df = compute_cumulative(df) if not df.empty else df
    daily = calculate_daily_pnl(df)
    risk_metrics = calculate_risk_metrics(df)

    all_time = 0.0
    if not df.empty and "Computed_Cum" in df.columns and df["Computed_Cum"].dropna().any():
        vals = df["Computed_Cum"].dropna()
        all_time = float(vals.iloc[-1]) if not vals.empty else 0.0
    elif not df.empty and df["NetPnl_num"].notnull().any():
        all_time = float(df["NetPnl_num"].dropna().sum())

    open_trades = get_open_trades_with_pnl()
    
    open_html = "<p>No open positions</p>"
    if open_trades:
        opens = []
        for trade in open_trades:
            symbol = trade["symbol"]
            side = trade["side"].upper()
            entry_price = trade["entry_price"]
            current_price = trade["current_price"]
            pnl = trade["pnl"]
            pnl_percent = trade["pnl_percent"]
            sl = trade.get("sl", 0)
            tp1 = trade.get("tp1", 0)
            tp2 = trade.get("tp2", 0)
            tp3 = trade.get("tp3", 0)
            trailing_active = trade.get("trailing_active", False)
            remaining_quantity = trade.get("remaining_quantity", 0)
            
            pnl_class = "positive" if pnl >= 0 else "negative"
            trailing_badge = " 🚀" if trailing_active else ""
            
            tp_targets = trade.get("tp_targets", {})
            if tp_targets and tp_targets.get("tp1", {}).get("hit", False):
                sl_display_value = entry_price
                sl_placeholder = f"Entry: {entry_price:.4f}"
            else:
                sl_display_value = sl
                sl_placeholder = "Stop Loss"
            
            opens.append(f"""
            <div class="position-card">
                <div class="position-header">
                    <span class="symbol">{symbol}</span>
                    <span class="side {side.lower()}">{side}{trailing_badge}</span>
                </div>
                <div class="position-details">
                    <div>Entry: <strong>{entry_price:.4f}</strong></div>
                    <div>Current: <strong>{current_price:.4f}</strong></div>
                    <div>Remaining: <strong>{remaining_quantity:.6f}</strong></div>
                    <div>Unrealized P&L: <span class='{pnl_class}'>{pnl:+.2f} USDT ({pnl_percent:+.2f}%)</span></div>
                </div>
                <div class="tp-levels">
                    <div class="tp-level">
                        <span class="tp-label">SL:</span>
                        <span class="tp-value">{sl_display_value:.4f}</span>
                    </div>
                    <div class="tp-level">
                        <span class="tp-label">TP1:</span>
                        <span class="tp-value">{tp1:.4f}</span>
                    </div>
                    <div class="tp-level">
                        <span class="tp-label">TP2:</span>
                        <span class="tp-value">{tp2:.4f}</span>
                    </div>
                    <div class="tp-level">
                        <span class="tp-label">TP3:</span>
                        <span class="tp-value">{tp3:.4f}</span>
                    </div>
                </div>
                <div class="position-controls">
                    <div class="sltp-controls-horizontal">
                        <div class="control-group">
                            <label>SL:</label>
                            <input type="text" id="sl_{symbol}" value="{sl_display_value:.4f}" placeholder="{sl_placeholder}">
                        </div>
                        <div class="control-group">
                            <label>TP1:</label>
                            <input type="text" id="tp1_{symbol}" value="{tp1:.4f}" placeholder="Take Profit 1">
                        </div>
                        <div class="control-group">
                            <label>TP2:</label>
                            <input type="text" id="tp2_{symbol}" value="{tp2:.4f}" placeholder="Take Profit 2">
                        </div>
                        <div class="control-group">
                            <label>TP3:</label>
                            <input type="text" id="tp3_{symbol}" value="{tp3:.4f}" placeholder="Take Profit 3">
                        </div>
                        <button class="btn-secondary" onclick="updateSLTP('{symbol}')">Update SL/TP</button>
                        <button class="btn-danger" onclick="closeTrade('{symbol}')">Close Trade</button>
                    </div>
                </div>
            </div>
            """)
        
        open_html = f"""
        <div class="positions-grid">
            {''.join(opens)}
        </div>
        """

    # Summary table
    summary_html = "<div class='summary-table'><h4>Trade Summary</h4><table>"
    summary_html += "<tr><th>Type</th><th>Total</th><th>Success</th><th>SL Hit</th><th>Win%</th><th>Loss%</th></tr>"
    
    exit_trades = df[df["Signal"].str.contains("Exit|Close", na=False)]
    long_trades = exit_trades[exit_trades["Side"].str.upper()=="LONG"]
    short_trades = exit_trades[exit_trades["Side"].str.upper()=="SHORT"]
    
    def summary_row(df_side, typ):
        total = len(df_side)
        success = len(df_side[df_side["NetPnl_num"]>0])
        sl_hit = len(df_side[df_side["NetPnl_num"]<0])
        win_pct = f"{(success/total*100):.1f}%" if total>0 else "0%"
        loss_pct = f"{(sl_hit/total*100):.1f}%" if total>0 else "0%"
        return f"<tr><td>{typ}</td><td>{total}</td><td class='positive'>{success}</td><td class='negative'>{sl_hit}</td><td>{win_pct}</td><td>{loss_pct}</td></tr>"
    
    if not long_trades.empty:
        summary_html += summary_row(long_trades,"LONG")
    if not short_trades.empty:
        summary_html += summary_row(short_trades,"SHORT")
    summary_html += "</table></div>"

    # Risk Metrics
    risk_metrics_html = ""
    if risk_metrics:
        risk_metrics_html = f"""
        <div class="risk-metrics">
            <h4>📊 Risk Metrics</h4>
            <div class="metrics-grid">
                <div class="metric-card">
                    <span class="metric-label">Win Rate</span>
                    <span class="metric-value">{risk_metrics.get('win_rate', 0):.1f}%</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Profit Factor</span>
                    <span class="metric-value">{risk_metrics.get('profit_factor', 0):.2f}</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Avg Win</span>
                    <span class="metric-value positive">{risk_metrics.get('avg_win', 0):.2f}</span>
                </div>
                <div class="metric-card">
                    <span class="metric-label">Avg Loss</span>
                    <span class="metric-value negative">{risk_metrics.get('avg_loss', 0):.2f}</span>
                </div>
            </div>
        </div>
        """

    trade_history_html = format_trade_history(df)
    completed_trades_count = len(df[df["Signal"].str.contains("Exit|Close", na=False)])

    html = f"""
    <html>
    <head>
        <title>Rafique Trading Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            :root {{
                --primary: #2563eb;
                --success: #10b981;
                --danger: #ef4444;
                --warning: #f59e0b;
                --dark: #1f2937;
                --light: #f3f4f6;
            }}
            
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}
            
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                height: 100vh;
                overflow: hidden;
                color: #333;
            }}
            
            .container {{
                max-width: 1800px;
                margin: 0 auto;
                background: white;
                height: 100vh;
                display: flex;
                flex-direction: column;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }}
            
            .header {{
                background: var(--dark);
                color: white;
                padding: 10px 15px;
                text-align: center;
                flex-shrink: 0;
            }}
            
            .header h1 {{
                margin: 0;
                font-size: 1.5em;
                font-weight: 300;
            }}
            
            .main-content {{
                padding: 10px;
                display: flex;
                flex-direction: column;
                height: calc(100vh - 60px);
                overflow: hidden;
                gap: 10px;
            }}
            
            /* TOP SECTION - Fixed height, no scroll */
            .dashboard-top {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
                height: 280px;  /* Reduced height to make space for trade history */
                flex-shrink: 0;
            }}
            
            .left-panel {{
                display: flex;
                flex-direction: column;
                gap: 10px;
            }}
            
            .right-panel {{
                display: flex;
                flex-direction: column;
                gap: 10px;
            }}
            
            .stats-overview {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 8px;
            }}
            
            .stat-card {{
                background: white;
                padding: 8px;
                border-radius: 6px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                text-align: center;
                border-left: 3px solid var(--primary);
            }}
            
            .stat-card h3 {{
                color: var(--dark);
                margin-bottom: 3px;
                font-size: 0.7em;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            
            .stat-card .value {{
                font-size: 1.1em;
                font-weight: bold;
            }}
            
            .positive {{ color: var(--success); }}
            .negative {{ color: var(--danger); }}
            
            .section {{
                background: white;
                padding: 8px;
                border-radius: 6px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                flex: 1;
                display: flex;
                flex-direction: column;
                min-height: 0;
            }}
            
            .section h3 {{
                color: var(--dark);
                margin-bottom: 6px;
                padding-bottom: 4px;
                border-bottom: 1px solid var(--light);
                font-size: 0.9em;
                flex-shrink: 0;
            }}
            
            /* Open Positions */
            .positions-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 8px;
                overflow-y: auto;
                flex: 1;
                padding: 3px;
            }}
            
            .position-card {{
                border: 1px solid #e5e7eb;
                border-radius: 5px;
                padding: 8px;
                background: #fafafa;
                min-height: 180px;
            }}
            
            .position-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 6px;
            }}
            
            .symbol {{
                font-weight: bold;
                font-size: 0.8em;
            }}
            
            .side.long {{ color: var(--success); }}
            .side.short {{ color: var(--danger); }}
            
            .position-details div {{
                margin: 2px 0;
                font-size: 0.75em;
            }}
            
            .tp-levels {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 2px;
                margin: 6px 0;
                padding: 4px;
                background: #f8fafc;
                border-radius: 3px;
                border: 1px solid #e2e8f0;
            }}
            
            .tp-level {{
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            
            .tp-label {{
                font-size: 0.65em;
                color: #64748b;
                font-weight: 600;
            }}
            
            .tp-value {{
                font-size: 0.7em;
                font-weight: bold;
                color: #1e293b;
            }}
            
            .sltp-controls-horizontal {{
                display: flex;
                gap: 4px;
                align-items: center;
                flex-wrap: wrap;
                margin-top: 6px;
            }}
            
            .control-group {{
                display: flex;
                flex-direction: column;
                gap: 1px;
            }}
            
            .control-group label {{
                font-size: 0.55em;
                color: #666;
                font-weight: 600;
            }}
            
            .sltp-controls-horizontal input {{
                width: 55px;
                padding: 2px;
                border: 1px solid #ccc;
                border-radius: 2px;
                font-size: 0.65em;
                text-align: center;
            }}
            
            button {{
                padding: 3px 6px;
                border: none;
                border-radius: 2px;
                cursor: pointer;
                font-size: 0.65em;
                transition: all 0.3s ease;
                white-space: nowrap;
            }}
            
            .btn-secondary {{
                background: var(--primary);
                color: white;
            }}
            
            .btn-danger {{
                background: var(--danger);
                color: white;
            }}
            
            .btn-export {{
                background: var(--warning);
                color: white;
            }}
            
            /* Summary and Risk Metrics */
            .summary-table table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 0.7em;
            }}
            
            .summary-table th, .summary-table td {{
                border: 1px solid #e5e7eb;
                padding: 4px;
                text-align: center;
            }}
            
            .summary-table th {{
                background: var(--light);
                font-weight: 600;
            }}
            
            .metrics-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 6px;
            }}
            
            .metric-card {{
                background: var(--light);
                padding: 6px;
                border-radius: 4px;
                text-align: center;
                border-left: 2px solid var(--primary);
            }}
            
            .metric-label {{
                display: block;
                font-size: 0.6em;
                color: #666;
                margin-bottom: 2px;
            }}
            
            .metric-value {{
                display: block;
                font-size: 0.8em;
                font-weight: bold;
            }}
            
            .controls {{
                display: flex;
                gap: 6px;
                margin-bottom: 8px;
                flex-wrap: wrap;
                flex-shrink: 0;
            }}
            
            .search-box {{
                padding: 4px 8px;
                border: 1px solid #ccc;
                border-radius: 3px;
                flex: 1;
                min-width: 120px;
                font-size: 0.75em;
            }}
            
            .filter-select {{
                padding: 4px 8px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background: white;
                font-size: 0.75em;
            }}
            
            .export-buttons {{
                display: flex;
                gap: 6px;
            }}
            
            /* BOTTOM SECTION - Trade History with Scroll - BIGGER HEIGHT */
            .trade-history-section {{
                flex: 1;
                display: flex;
                flex-direction: column;
                min-height: 0;
                height: calc(100vh - 400px); /* Increased height for trade history */
            }}
            
            .trade-history-container {{
                flex: 1;
                overflow: auto;
                border: 1px solid #e5e7eb;
                border-radius: 5px;
                max-height: none;
            }}
            
            .trade-table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 0.75em; /* Slightly larger font for better readability */
                table-layout: fixed;
                margin: 0;
            }}
            
            .trade-table th, .trade-table td {{
                padding: 6px 8px; /* More padding for better spacing */
                border: 1px solid #e5e7eb;
                text-align: left;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }}
            
            .trade-table th {{
                background: #f8fafc;
                font-weight: 600;
                color: #374151;
                position: sticky;
                top: 0;
                z-index: 10;
                font-size: 0.8em; /* Slightly larger header font */
            }}
            
            .col-trade-no {{ width: 70px; text-align: center; }}
            .col-symbol {{ width: 100px; }}
            .col-type {{ width: 70px; text-align: center; }}
            .col-date {{ width: 130px; }}
            .col-signal {{ width: 90px; text-align: center; }}
            .col-price {{ width: 100px; text-align: right; }}
            .col-size {{ width: 100px; text-align: right; }}
            .col-pnl {{ width: 90px; text-align: center; }}
            .col-runup {{ width: 90px; text-align: center; }}
            .col-drawdown {{ width: 90px; text-align: center; }}
            .col-cumulative {{ width: 100px; text-align: right; }}
            
            .trade-row {{
                transition: background-color 0.2s;
            }}
            
            .trade-row:hover {{
                background-color: #f9fafb;
            }}
            
            .entry-row {{
                background-color: #ffffff;
            }}
            
            .entry-row.long {{
                border-left: 3px solid #10b981;
            }}
            
            .entry-row.short {{
                border-left: 3px solid #ef4444;
            }}
            
            .exit-row {{
                background-color: #f8fafc;
                color: #6b7280;
            }}
            
            @media (max-width: 1200px) {{
                .dashboard-top {{
                    grid-template-columns: 1fr;
                    height: auto;
                }}
                
                .positions-grid {{
                    grid-template-columns: 1fr;
                }}
                
                .trade-history-section {{
                    height: auto;
                    min-height: 300px;
                }}
            }}
        </style>
        <meta http-equiv="refresh" content="15">
        <script>
        function updateSLTP(sym) {{
            let sl = document.getElementById("sl_"+sym).value;
            let tp1 = document.getElementById("tp1_"+sym).value;
            let tp2 = document.getElementById("tp2_"+sym).value;
            let tp3 = document.getElementById("tp3_"+sym).value;
            
            fetch(`/update_sltp/${{sym}}`, {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{
                    sl: sl,
                    tp1: tp1,
                    tp2: tp2,
                    tp3: tp3
                }})
            }})
            .then(r => r.json())
            .then(d => {{
                if(d.status === 'ok') {{
                    alert('SL/TP updated successfully!');
                    location.reload();
                }} else {{
                    alert('Error updating SL/TP: ' + d.message);
                }}
            }})
            .catch(error => {{
                alert('Error updating SL/TP: ' + error);
            }});
        }}
        
        function closeTrade(sym) {{
            if(confirm('Are you sure you want to close this trade?')) {{
                fetch('/close_trade/'+sym, {{ method: 'POST' }})
                    .then(r => r.json())
                    .then(d => {{
                        if(d.status === 'ok') {{
                            alert('Trade closed successfully!');
                            location.reload();
                        }} else {{
                            alert('Error closing trade: ' + d.message);
                        }}
                    }})
                    .catch(error => {{
                        alert('Error closing trade: ' + error);
                    }});
            }}
        }}
        
        function searchTrades() {{
            const input = document.getElementById('searchInput');
            const filter = input.value.toLowerCase();
            const table = document.getElementById('tradesTable');
            const tr = table.getElementsByTagName('tr');
            
            for (let i = 1; i < tr.length; i++) {{
                const td = tr[i].getElementsByTagName('td');
                let found = false;
                for (let j = 0; j < td.length; j++) {{
                    if (td[j]) {{
                        if (td[j].textContent.toLowerCase().indexOf(filter) > -1) {{
                            found = true;
                            break;
                        }}
                    }}
                }}
                tr[i].style.display = found ? '' : 'none';
            }}
        }}
        
        function exportTrades(format) {{
            fetch(`/export/trades?format=${{format}}`)
                .then(response => response.json())
                .then(data => {{
                    if(data.content) {{
                        const blob = new Blob([data.content], {{ type: 'text/plain' }});
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.style.display = 'none';
                        a.href = url;
                        a.download = data.filename || `trades.${{format}}`;
                        document.body.appendChild(a);
                        a.click();
                        window.URL.revokeObjectURL(url);
                    }}
                }});
        }}
        
        function populateSymbolFilter() {{
            const filter = document.getElementById('symbolFilter');
            const symbols = new Set();
            const table = document.getElementById('tradesTable');
            const tr = table.getElementsByTagName('tr');
            
            for (let i = 1; i < tr.length; i++) {{
                const td = tr[i].getElementsByTagName('td');
                if(td[1]) {{
                    const symbol = td[1].textContent.split(' ')[0];
                    if(symbol) symbols.add(symbol);
                }}
            }}
            
            symbols.forEach(symbol => {{
                const option = document.createElement('option');
                option.value = symbol;
                option.textContent = symbol;
                filter.appendChild(option);
            }});
        }}
        
        function filterTrades() {{
            const symbolFilter = document.getElementById('symbolFilter').value;
            const sideFilter = document.getElementById('sideFilter').value;
            const table = document.getElementById('tradesTable');
            const tr = table.getElementsByTagName('tr');
            
            for (let i = 1; i < tr.length; i++) {{
                const td = tr[i].getElementsByTagName('td');
                let show = true;
                
                if(symbolFilter && td[1]) {{
                    const symbol = td[1].textContent.split(' ')[0];
                    if(symbol !== symbolFilter) show = false;
                }}
                
                if(sideFilter && td[2]) {{
                    const side = td[2].textContent;
                    if(side !== sideFilter) show = false;
                }}
                
                tr[i].style.display = show ? '' : 'none';
            }}
        }}
        
        document.addEventListener('DOMContentLoaded', function() {{
            populateSymbolFilter();
        }});
        </script>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 Rafique Trading Dashboard</h1>
                <p>Multi-TP + Trailing Stop System</p>
            </div>
            
            <div class="main-content">
                <div class="controls">
                    <input type="text" id="searchInput" class="search-box" placeholder="🔍 Search trades..." onkeyup="searchTrades()">
                    <select id="symbolFilter" class="filter-select" onchange="filterTrades()">
                        <option value="">All Symbols</option>
                    </select>
                    <select id="sideFilter" class="filter-select" onchange="filterTrades()">
                        <option value="">All Sides</option>
                        <option value="LONG">LONG</option>
                        <option value="SHORT">SHORT</option>
                    </select>
                    <div class="export-buttons">
                        <button class="btn-export" onclick="exportTrades('csv')">Export CSV</button>
                        <button class="btn-export" onclick="exportTrades('json')">Export JSON</button>
                    </div>
                </div>
                
                <div class="dashboard-top">
                    <div class="left-panel">
                        <div class="stats-overview">
                            <div class="stat-card">
                                <h3>All Time P&L</h3>
                                <div class="value {'positive' if all_time >= 0 else 'negative'}">{all_time:.2f} USDT</div>
                            </div>
                            <div class="stat-card">
                                <h3>Total Trades</h3>
                                <div class="value">{completed_trades_count}</div>
                            </div>
                            <div class="stat-card">
                                <h3>Win Rate</h3>
                                <div class="value">{risk_metrics.get('win_rate', 0):.1f}%</div>
                            </div>
                            <div class="stat-card">
                                <h3>Profit Factor</h3>
                                <div class="value">{risk_metrics.get('profit_factor', 0):.2f}</div>
                            </div>
                        </div>
                        
                        <div class="section">
                            <h3>📊 Performance Analytics</h3>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; height: 100%;">
                                {summary_html}
                                {risk_metrics_html}
                            </div>
                        </div>
                    </div>
                    
                    <div class="right-panel">
                        <div class="section">
                            <h3>📈 Open Positions ({len(open_trades)})</h3>
                            {open_html}
                        </div>
                    </div>
                </div>
                
                {trade_history_html}
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)

# ... (rest of the API endpoints remain the same as previous code)
@app.get("/api/trades")
def api_trades():
    df = load_trades()
    if df.empty: 
        return JSONResponse([])

    out = df.copy()
    if "__dt_parsed" in out.columns:
        out["__dt_parsed"] = out["__dt_parsed"].apply(lambda x: x.isoformat() if pd.notna(x) else None)
    for col in out.select_dtypes(include=['float','int']).columns:
        out[col] = out[col].apply(lambda x: float(x) if pd.notna(x) and abs(x) != float('inf') else None)
    return JSONResponse(out.to_dict(orient="records"))

@app.get("/api/open-trades")
def api_open_trades():
    open_trades = get_open_trades_with_pnl()
    return JSONResponse(open_trades)

@app.post("/close_trade/{symbol}")
def close_trade(symbol: str):
    try:
        state = load_state()
        open_trades = state.get("open_trades", {})
        
        if symbol in open_trades:
            trade_info = open_trades[symbol]
            entry_price = safe_float_convert(trade_info.get("entry_price", 0))
            quantity = safe_float_convert(trade_info.get("remaining_quantity") or trade_info.get("quantity", 0))
            side = trade_info.get("side", "")
            trade_num = trade_info.get("trade_num", 0)
            
            current_price = get_current_price(symbol)
            if current_price is None:
                current_price = entry_price
            
            if side == "long":
                pnl = (current_price - entry_price) * quantity
            else:
                pnl = (entry_price - current_price) * quantity
            
            del open_trades[symbol]
            save_state(state)
            
            try:
                exit_row = {
                    "Trade #": str(trade_num),
                    "Symbol": symbol.replace('USDT', ''),
                    "Side": side.upper(),
                    "Type": f"{symbol} {side.upper()}",
                    "Date/Time": datetime.now().strftime("%b %d, %Y, %H:%M"),
                    "Signal": "Exit",
                    "Price": f"{current_price:.8f}",
                    "Position size": f"{quantity:.6f} ({round(quantity*current_price,2):.2f} USDT)",
                    "Net P&L": f"{pnl:+.2f} USDT",
                    "Run-up": "0",
                    "Drawdown": "0",
                    "Cumulative P&L": ""
                }
                
                append_trade_row(exit_row)
                
            except Exception as e:
                print(f"Error logging trade closure: {e}")
            
            return {"status": "ok", "message": f"Trade {symbol} closed successfully", "pnl": round(pnl, 2)}
        else:
            return {"status": "error", "message": "Trade not found in open positions"}
            
    except Exception as e:
        return {"status": "error", "message": f"Error closing trade: {str(e)}"}

@app.post("/update_sltp/{symbol}")
async def update_sltp(symbol: str, request: Request):
    """Update Stop Loss and Take Profit for a trade"""
    try:
        body = await request.json()
        sl = body.get("sl", "")
        tp1 = body.get("tp1", "")
        tp2 = body.get("tp2", "")
        tp3 = body.get("tp3", "")
        
        state = load_state()
        open_trades = state.get("open_trades", {})
        
        if symbol in open_trades:
            if sl:
                try:
                    sl_float = float(sl)
                    state["open_trades"][symbol]["sl"] = f"{sl_float:.4f}"
                except ValueError:
                    return {"status": "error", "message": "Invalid SL format"}
            
            if tp1:
                try:
                    tp1_float = float(tp1)
                    state["open_trades"][symbol]["tp1"] = f"{tp1_float:.4f}"
                except ValueError:
                    return {"status": "error", "message": "Invalid TP1 format"}
            
            if tp2:
                try:
                    tp2_float = float(tp2)
                    state["open_trades"][symbol]["tp2"] = f"{tp2_float:.4f}"
                except ValueError:
                    return {"status": "error", "message": "Invalid TP2 format"}
            
            if tp3:
                try:
                    tp3_float = float(tp3)
                    state["open_trades"][symbol]["tp3"] = f"{tp3_float:.4f}"
                except ValueError:
                    return {"status": "error", "message": "Invalid TP3 format"}
            
            save_state(state)
            print(f"SL/TP updated for {symbol}: SL={sl}, TP1={tp1}, TP2={tp2}, TP3={tp3}")
            return {"status": "ok", "symbol": symbol, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3}
        return {"status": "error", "message": "Symbol not found in open trades"}
    except Exception as e:
        print(f"Error updating SL/TP: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/export/trades")
def export_trades(format: str = "csv"):
    df = load_trades()
    if format == "csv":
        csv_content = df.to_csv(index=False)
        return JSONResponse({"content": csv_content, "filename": "trades.csv"})
    elif format == "json":
        json_content = df.to_json(orient="records", indent=2)
        return JSONResponse({"content": json_content, "filename": "trades.json"})
    else:
        return JSONResponse({"error": "Unsupported format"}, status_code=400)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)