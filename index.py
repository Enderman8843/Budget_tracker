import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, Response, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import pandas as pd
from sklearn.linear_model import LinearRegression
import numpy as np
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'secret'
DB_NAME = 'budget.db'

# minimal currency symbol map
CURRENCY_SYMBOL_MAP = {
    'INR': '₹',
    'USD': '$',
    'EUR': '€',
    'GBP': '£',
    'JPY': '¥'
}


def get_db():
    conn = sqlite3.connect(DB_NAME)
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    type TEXT,
                    amount REAL,
                    category TEXT,
                    description TEXT,
                    date TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    category TEXT,
                    monthly_limit REAL
                )''')
    conn.commit()
    conn.close()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/register', methods=['GET', 'POST'])
def register():
    # Redirect if already logged in
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        if not username or not password:
            flash("Username and password are required", "error")
            return redirect(url_for('register'))

        password_hash = generate_password_hash(password)

        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password_hash))
            conn.commit()
            flash("Account created successfully. Please log in.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already exists. Please choose another.", "error")
            return redirect(url_for('register'))
        finally:
            conn.close()

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    # Redirect if already logged in
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        if not username or not password:
            flash("Please enter both username and password", "error")
            return redirect(url_for('login'))

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, password FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            session['username'] = username
            flash("Logged in successfully!", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid username or password", "error")
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/set_currency/<currency_code>')
def set_currency(currency_code):
    session['currency'] = (currency_code or 'INR').upper()
    return redirect(request.referrer or url_for('index'))


def expense_forecast(user_id, start=None, end=None):
    conn = get_db()
    c = conn.cursor()
    q = "SELECT amount, date FROM transactions WHERE user_id=? AND type='expense'"
    p = [user_id]
    if start and end:
        q += " AND date BETWEEN ? AND ?"
        p += [start, end]
    c.execute(q, p)
    rows = c.fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=['amount', 'date'])
    if df.empty:
        return None
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    monthly = df.groupby(pd.Grouper(key='date', freq='MS'))['amount'].sum().reset_index()
    if len(monthly) < 2:
        return None
    X = np.arange(len(monthly)).reshape(-1, 1)
    model = LinearRegression().fit(X, monthly['amount'])
    return round(max(model.predict([[len(monthly)]])[0], 0), 2)


def highest_spending_category(df, currency_symbol):
    """Return string like 'Food – ₹123.45' or None if no expense data."""
    if df.empty:
        return None
    exp = df[df['type'] == 'expense']
    if exp.empty:
        return None
    # ensure column names are lowercase 'category' and 'amount'
    grouped = exp.groupby('category')['amount'].sum()
    if grouped.empty:
        return None
    cat = grouped.idxmax()
    amt = grouped.max()
    return f"{cat} – {currency_symbol}{round(amt, 2)}"


def avg_daily_spend(df):
    if df.empty:
        return 0
    exp = df[df['type'] == 'expense']
    if exp.empty:
        return 0
    # make sure date is datetime
    if exp['date'].dtype == object:
        exp['date'] = pd.to_datetime(exp['date'], errors='coerce')
    daily = exp.groupby(exp['date'].dt.date)['amount'].sum()
    if daily.empty:
        return 0
    return round(daily.mean(), 2)


@app.route('/delete/<int:tx_id>', methods=['POST'])
@login_required
def delete_transaction(tx_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM transactions WHERE id=? AND user_id=?", (tx_id, session['user_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))


@app.route('/')
@login_required
def index():
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    currency = session.get('currency', 'INR')  # default INR
    currency_symbol = CURRENCY_SYMBOL_MAP.get(currency, currency)

    conn = get_db()
    c = conn.cursor()
    q = "SELECT id, type, amount, category, description, date FROM transactions WHERE user_id=?"
    p = [session['user_id']]
    if start_date and end_date:
        q += " AND date BETWEEN ? AND ?"
        p += [start_date, end_date]
    q += " ORDER BY date DESC"
    c.execute(q, p)
    rows = c.fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=['id', 'type', 'amount', 'category', 'description', 'date'])
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')

    income = round(df[df['type'] == 'income']['amount'].sum(), 2) if not df.empty else 0
    expense = round(df[df['type'] == 'expense']['amount'].sum(), 2) if not df.empty else 0
    balance = round(income - expense, 2)

    forecast = expense_forecast(session['user_id'], start_date, end_date)

    ai_insights = {
        "Highest Spending Category": highest_spending_category(df, currency_symbol) or "N/A",
        "Average Daily Spend": f"{currency_symbol}{avg_daily_spend(df)}",
        "Expense Forecast": f"{currency_symbol}{forecast}" if forecast else "Not enough data",
        "Transactions Found": len(df) if not df.empty else 0
    }

    # time label logic (safely handle missing/partial dates)
    if not start_date or not end_date:
        time_label = "All Time"
    else:
        try:
            start_d = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
            end_d = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
            if start_d.date() == end_d.date():
                time_label = "Day View"
            elif (end_d - start_d).days <= 7:
                time_label = "Week View"
            else:
                time_label = "Month View"
        except Exception:
            time_label = "Custom Range"

    return render_template('index.html',
                           income=income,
                           expense=expense,
                           balance=balance,
                           transactions=df.to_dict(orient='records'),
                           ai_insights=ai_insights,
                           time_range_label=time_label,
                           currency=currency,
                           currency_symbol=currency_symbol
                           )


@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_entry():
    if request.method == 'POST':
        ttype = request.form['type']
        amount = float(request.form['amount'])
        category = request.form['category']
        description = request.form['description']
        date = request.form.get('date') or datetime.today().strftime('%Y-%m-%d %H:%M:%S')

        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO transactions (user_id, type, amount, category, description, date) VALUES (?,?,?,?,?,?)",
                  (session['user_id'], ttype, amount, category, description, date))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    return render_template('add.html')


@app.route('/export_csv')
@login_required
def export_csv():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT type, amount, category, description, date FROM transactions WHERE user_id=?", (session['user_id'],))
    rows = c.fetchall()
    conn.close()
    df = pd.DataFrame(rows, columns=['Type', 'Amount', 'Category', 'Description', 'Date'])
    csv_data = df.to_csv(index=False)
    return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=transactions.csv"})


if __name__ == '__main__':
    init_db()
    app.run()
