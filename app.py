import csv
from datetime import date, datetime
from functools import wraps
import io
import json
import os
import sqlite3
from flask import Flask, flash, make_response, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "home-budget-verified-secret-key-2026"

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "home_budget.db")

# 17 Project Specification Categories & 6 Payment Methods
CATEGORIES = [
    "Food & Groceries", "Rent", "Electricity", "Water", "Internet & Mobile",
    "Transportation", "Fuel", "Education", "Healthcare", "Shopping",
    "Entertainment", "Household Supplies", "Insurance", "EMI & Loans",
    "Travel", "Personal Care", "Other"
]

PAYMENT_METHODS = ["Cash", "UPI", "Debit Card", "Credit Card", "Bank Transfer", "Other"]

# ---------------------------------------------------------------------------
# DATABASE INITIALIZATION & PRE-LOADED DEMO DATA
# ---------------------------------------------------------------------------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        cur = conn.cursor()

        # Users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Expenses table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                category TEXT NOT NULL,
                expense_date TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        # Budgets table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
                year INTEGER NOT NULL,
                budget_amount REAL NOT NULL CHECK(budget_amount >= 0),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, month, year),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        # Insert demo account & sample transactions if not already populated
        cur.execute("SELECT id FROM users WHERE username = 'demo_user'")
        if not cur.fetchone():
            demo_pw = generate_password_hash("student123")
            cur.execute("""
                INSERT INTO users (username, full_name, password_hash)
                VALUES ('demo_user', 'Demo Student', ?)
            """, (demo_pw,))
            uid = cur.lastrowid
            today = date.today()

            # Set monthly budget of ₹25,000 for current month
            cur.execute("""
                INSERT OR REPLACE INTO budgets (user_id, month, year, budget_amount)
                VALUES (?, ?, ?, 25000.00)
            """, (uid, today.month, today.year))

            # Sample expenses matching project specifications
            sample_records = [
                (uid, "Monthly Supermarket Groceries", 5400.00, "Food & Groceries", today.isoformat(), "UPI", "D-Mart grocery provisions"),
                (uid, "Apartment House Rent", 8500.00, "Rent", today.isoformat(), "Bank Transfer", "Monthly house rent"),
                (uid, "Electricity Bill", 1450.00, "Electricity", today.isoformat(), "UPI", "Power bill"),
                (uid, "Fiber Broadband", 799.00, "Internet & Mobile", today.isoformat(), "Credit Card", "High-speed internet"),
                (uid, "Motorbike Fuel", 650.00, "Fuel", today.isoformat(), "UPI", "Petrol bunk refill"),
                (uid, "DBMS Reference Textbook", 1200.00, "Education", today.isoformat(), "Debit Card", "Semester academic books"),
                (uid, "Health Pharmacy & Medicine", 850.00, "Healthcare", today.isoformat(), "Cash", "Apollo Pharmacy"),
                (uid, "Weekend Movie & Snacks", 450.00, "Entertainment", today.isoformat(), "UPI", "Cinema tickets and popcorn")
            ]
            cur.executemany("""
                INSERT INTO expenses (user_id, title, amount, category, expense_date, payment_method, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, sample_records)

        conn.commit()

# Ensure database tables exist at startup
init_db()

# ---------------------------------------------------------------------------
# AUTHENTICATION DECORATOR & TEMPLATE ENGINE
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to access your budget dashboard.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

BASE_LAYOUT = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }} - Home Budget & Analysis</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { background-color: #f8fafc; font-family: 'Segoe UI', system-ui, sans-serif; }
    .card { border-radius: 12px; border: 1px solid #e2e8f0; }
  </style>
</head>
<body class="d-flex flex-column min-vh-100">
<nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4 shadow-sm">
  <div class="container">
    <a class="navbar-brand fw-bold text-success" href="{{ url_for('dashboard') }}">
      <i class="fa-solid fa-wallet me-2"></i>Home<span class="text-white">Budget</span>
    </a>
    {% if session.get('user_id') %}
    <div class="navbar-nav me-auto">
      <a class="nav-link" href="{{ url_for('dashboard') }}"><i class="fa-solid fa-chart-pie me-1"></i> Dashboard</a>
      <a class="nav-link" href="{{ url_for('expenses') }}"><i class="fa-solid fa-receipt me-1"></i> Expenses</a>
      <a class="nav-link" href="{{ url_for('budget') }}"><i class="fa-solid fa-bullseye me-1"></i> Budgets</a>
      <a class="nav-link" href="{{ url_for('analytics') }}"><i class="fa-solid fa-chart-line me-1"></i> Analytics</a>
      <a class="nav-link" href="{{ url_for('export_csv') }}"><i class="fa-solid fa-download me-1"></i> Export CSV</a>
    </div>
    <div class="d-flex align-items-center">
      <span class="text-light small me-3"><i class="fa-solid fa-user me-1"></i> {{ session.get('full_name') }}</span>
      <a class="btn btn-sm btn-outline-danger" href="{{ url_for('logout') }}">Logout</a>
    </div>
    {% endif %}
  </div>
</nav>

<div class="container pb-5 flex-grow-1">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="alert alert-{{ cat }} alert-dismissible fade show shadow-sm" role="alert">
        {{ msg }}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    {% endfor %}
  {% endwith %}
  <!-- CONTENT_PLACEHOLDER -->
</div>

<footer class="bg-white border-top py-3 text-center text-muted small mt-auto">
  Home Budget – Expenses Tracker and Analysis System &copy; 2026 | College DBMS + Python Project
</footer>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

def render_page(content_html, title="Home Budget", **context):
    full_html = BASE_LAYOUT.replace("<!-- CONTENT_PLACEHOLDER -->", content_html)
    return render_template_string(full_html, title=title, **context)

# ---------------------------------------------------------------------------
# CONTROLLERS & ROUTES
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("dashboard")) if "user_id" in session else redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        u = request.form.get("username", "").strip().lower()
        p = request.form.get("password", "")
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            user = conn.execute("SELECT * FROM users WHERE username = ?", (u,)).fetchone()
        if user and check_password_hash(user["password_hash"], p):
            session.clear()
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            session["username"] = user["username"]
            flash(f"Welcome back, {user['full_name']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")

    content = """
    <div class="row justify-content-center pt-4">
      <div class="col-md-5">
        <div class="card shadow-sm p-4">
          <div class="text-center mb-3">
            <i class="fa-solid fa-vault fa-3x text-primary mb-2"></i>
            <h3 class="fw-bold">Sign In</h3>
            <p class="text-muted small">Preloaded Demo: <strong>demo_user</strong> / <strong>student123</strong></p>
          </div>
          <form method="post">
            <div class="mb-3">
              <label class="form-label fw-semibold">Username</label>
              <input type="text" name="username" class="form-control" required autofocus placeholder="demo_user">
            </div>
            <div class="mb-3">
              <label class="form-label fw-semibold">Password</label>
              <input type="password" name="password" class="form-control" required placeholder="••••••••">
            </div>
            <button type="submit" class="btn btn-primary w-100 py-2 fw-semibold">Sign In</button>
          </form>
          <div class="text-center mt-3 small">
            Need an account? <a href="{{ url_for('register') }}">Create new account</a>
          </div>
        </div>
      </div>
    </div>
    """
    return render_page(content, title="Sign In")

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        fn = request.form.get("full_name", "").strip()
        u = request.form.get("username", "").strip().lower()
        p = request.form.get("password", "")
        if not fn or not u or not p:
            flash("All fields are required.", "danger")
        else:
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("""
                        INSERT INTO users (full_name, username, password_hash)
                        VALUES (?, ?, ?)
                    """, (fn, u, generate_password_hash(p)))
                    conn.commit()
                flash("Account registered successfully! You can now sign in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("Username is already taken. Please choose another.", "danger")

    content = """
    <div class="row justify-content-center pt-4">
      <div class="col-md-5">
        <div class="card shadow-sm p-4">
          <div class="text-center mb-3">
            <i class="fa-solid fa-user-plus fa-3x text-success mb-2"></i>
            <h3 class="fw-bold">Create Account</h3>
            <p class="text-muted small">Register to track household budgets and analyze spending</p>
          </div>
          <form method="post">
            <div class="mb-3">
              <label class="form-label fw-semibold">Full Name</label>
              <input type="text" name="full_name" class="form-control" placeholder="e.g. Siva Kumar" required>
            </div>
            <div class="mb-3">
              <label class="form-label fw-semibold">Username</label>
              <input type="text" name="username" class="form-control" placeholder="Choose a username" required>
            </div>
            <div class="mb-3">
              <label class="form-label fw-semibold">Password</label>
              <input type="password" name="password" class="form-control" placeholder="Choose a password" required>
            </div>
            <button type="submit" class="btn btn-success w-100 py-2 fw-semibold">Register</button>
          </form>
          <div class="text-center mt-3 small">
            Already have an account? <a href="{{ url_for('login') }}">Sign In</a>
          </div>
        </div>
      </div>
    </div>
    """
    return render_page(content, title="Register")

@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    now = datetime.now()
    today_str = date.today().isoformat()
    month_prefix = f"{now.year}-{now.month:02d}"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        today_sum = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS val FROM expenses WHERE user_id = ? AND expense_date = ?",
            (uid, today_str)
        ).fetchone()["val"]

        month_sum = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS val, COUNT(id) AS cnt FROM expenses WHERE user_id = ? AND expense_date LIKE ?",
            (uid, f"{month_prefix}%")
        ).fetchone()

        all_sum = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS val, COUNT(id) AS cnt FROM expenses WHERE user_id = ?",
            (uid,)
        ).fetchone()

        b_row = conn.execute(
            "SELECT budget_amount FROM budgets WHERE user_id = ? AND month = ? AND year = ?",
            (uid, now.month, now.year)
        ).fetchone()

        recent = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY expense_date DESC, id DESC LIMIT 5",
            (uid,)
        ).fetchall()

    budget_amt = float(b_row["budget_amount"]) if b_row else 0.0
    m_spent = float(month_sum["val"])
    rem = budget_amt - m_spent if budget_amt > 0 else 0.0
    util = round((m_spent / budget_amt * 100), 1) if budget_amt > 0 else 0.0

    content = """
    <div class="d-flex justify-content-between align-items-center mb-4">
      <div>
        <h2 class="fw-bold mb-0">Financial Dashboard</h2>
        <p class="text-muted small mb-0">Overview for {{ month_name }}</p>
      </div>
      <a href="{{ url_for('add_expense') }}" class="btn btn-success shadow-sm">
        <i class="fa-solid fa-plus me-1"></i> Record New Expense
      </a>
    </div>

    <div class="row g-3 mb-4">
      <div class="col-md-3">
        <div class="card p-3 shadow-sm bg-white border-start border-primary border-4">
          <div class="text-muted small fw-bold">TODAY'S SPEND</div>
          <h3 class="text-primary mt-1">₹{{ "%.2f"|format(today_sum) }}</h3>
          <div class="text-muted small"><i class="fa-regular fa-clock me-1"></i> Recorded today</div>
        </div>
      </div>
      <div class="col-md-3">
        <div class="card p-3 shadow-sm bg-white border-start border-danger border-4">
          <div class="text-muted small fw-bold">MONTHLY TOTAL</div>
          <h3 class="text-danger mt-1">₹{{ "%.2f"|format(m_spent) }}</h3>
          <div class="text-muted small"><i class="fa-solid fa-calendar me-1"></i> {{ month_name }}</div>
        </div>
      </div>
      <div class="col-md-3">
        <div class="card p-3 shadow-sm bg-white border-start border-dark border-4">
          <div class="text-muted small fw-bold">OVERALL SPEND</div>
          <h3 class="text-dark mt-1">₹{{ "%.2f"|format(all_sum['val']) }}</h3>
          <div class="text-muted small"><i class="fa-solid fa-database me-1"></i> All-time total</div>
        </div>
      </div>
      <div class="col-md-3">
        <div class="card p-3 shadow-sm bg-white border-start border-info border-4">
          <div class="text-muted small fw-bold">TRANSACTIONS</div>
          <h3 class="text-info mt-1">{{ all_sum['cnt'] }}</h3>
          <div class="text-muted small"><i class="fa-solid fa-receipt me-1"></i> ({{ month_sum['cnt'] }} this month)</div>
        </div>
      </div>
    </div>

    <div class="card shadow-sm p-4 mb-4">
      <div class="d-flex justify-content-between align-items-center mb-2">
        <h5 class="fw-bold mb-0"><i class="fa-solid fa-bullseye text-primary me-2"></i>Monthly Budget Status</h5>
        <a href="{{ url_for('budget') }}" class="btn btn-sm btn-outline-secondary">Adjust Budget</a>
      </div>
      <div class="progress mb-2" style="height: 24px; border-radius: 8px;">
        <div class="progress-bar fw-bold {% if util > 100 %}bg-danger{% elif util >= 80 %}bg-warning text-dark{% else %}bg-success{% endif %}"
             style="width: {{ [util, 100]|min }}%;">
          {{ util }}%
        </div>
      </div>
      <div class="small text-muted">
        Spent: <strong>₹{{ "%.2f"|format(m_spent) }}</strong> / Budget: <strong>₹{{ "%.2f"|format(budget_amt) }}</strong> 
        (Remaining: <strong class="{{ 'text-success' if rem >= 0 else 'text-danger' }}">₹{{ "%.2f"|format(rem) }}</strong>)
      </div>
      {% if util > 100 %}
        <div class="alert alert-danger py-2 mt-2 mb-0 small"><i class="fa-solid fa-triangle-exclamation me-1"></i> <strong>Budget Exceeded Alert:</strong> You are over budget by ₹{{ "%.2f"|format(m_spent - budget_amt) }}!</div>
      {% elif util >= 80 %}
        <div class="alert alert-warning py-2 mt-2 mb-0 small"><i class="fa-solid fa-circle-exclamation me-1"></i> <strong>80% Budget Warning:</strong> You have consumed {{ util }}% of your allocated budget!</div>
      {% endif %}
    </div>

    <div class="card shadow-sm">
      <div class="card-header bg-white py-3 fw-bold"><i class="fa-solid fa-clock-rotate-left me-2 text-muted"></i>Recent Expenses</div>
      <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
          <thead class="table-light"><tr><th>Date</th><th>Title</th><th>Category</th><th>Payment</th><th class="text-end">Amount</th></tr></thead>
          <tbody>
            {% for r in recent %}
            <tr>
              <td>{{ r.expense_date }}</td>
              <td class="fw-semibold">{{ r.title }}</td>
              <td><span class="badge bg-secondary">{{ r.category }}</span></td>
              <td><span class="badge bg-light text-dark border">{{ r.payment_method }}</span></td>
              <td class="text-end fw-bold text-danger">₹{{ "%.2f"|format(r.amount) }}</td>
            </tr>
            {% else %}
            <tr><td colspan="5" class="text-center py-4 text-muted">No expenses recorded yet.</td></tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
    """
    return render_page(
        content,
        title="Dashboard",
        today_sum=today_sum,
        m_spent=m_spent,
        all_sum=all_sum,
        month_sum=month_sum,
        budget_amt=budget_amt,
        rem=rem,
        util=util,
        recent=recent,
        month_name=now.strftime("%B %Y")
    )

@app.route("/expenses")
@login_required
def expenses():
    uid = session["user_id"]
    keyword = request.args.get("keyword", "").strip()
    category = request.args.get("category", "").strip()

    sql = "SELECT * FROM expenses WHERE user_id = ?"
    params = [uid]

    if keyword:
        sql += " AND (title LIKE ? OR description LIKE ?)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if category:
        sql += " AND category = ?"
        params.append(category)

    sql += " ORDER BY expense_date DESC, id DESC"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()

    total_amount = sum(float(r["amount"]) for r in rows)

    content = """
    <div class="d-flex justify-content-between align-items-center mb-3">
      <div>
        <h2 class="fw-bold mb-0">Expense Ledger</h2>
        <p class="text-muted small mb-0">Found {{ rows|length }} records | Total: ₹{{ "%.2f"|format(total_amount) }}</p>
      </div>
      <a href="{{ url_for('add_expense') }}" class="btn btn-success"><i class="fa-solid fa-plus me-1"></i> Add Expense</a>
    </div>

    <div class="card p-3 mb-3 bg-white shadow-sm">
      <form method="get" class="row g-2">
        <div class="col-md-5">
          <input type="text" name="keyword" class="form-control form-control-sm" placeholder="Search title or notes..." value="{{ keyword }}">
        </div>
        <div class="col-md-4">
          <select name="category" class="form-select form-select-sm">
            <option value="">All Categories</option>
            {% for c in cats %}
              <option value="{{ c }}" {% if selected_category == c %}selected{% endif %}>{{ c }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="col-md-3 d-flex gap-2">
          <button type="submit" class="btn btn-sm btn-primary flex-grow-1"><i class="fa-solid fa-filter me-1"></i> Filter</button>
          <a href="{{ url_for('expenses') }}" class="btn btn-sm btn-outline-secondary">Reset</a>
        </div>
      </form>
    </div>

    <div class="card shadow-sm">
      <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
          <thead class="table-light"><tr><th>Date</th><th>Title</th><th>Category</th><th>Method</th><th>Notes</th><th class="text-end">Amount</th><th class="text-center">Action</th></tr></thead>
          <tbody>
            {% for r in rows %}
            <tr>
              <td>{{ r.expense_date }}</td>
              <td class="fw-semibold">{{ r.title }}</td>
              <td><span class="badge bg-secondary">{{ r.category }}</span></td>
              <td><span class="badge bg-light text-dark border">{{ r.payment_method }}</span></td>
              <td class="text-muted small">{{ r.description or '-' }}</td>
              <td class="text-end fw-bold text-danger">₹{{ "%.2f"|format(r.amount) }}</td>
              <td class="text-center">
                <form method="post" action="{{ url_for('delete_expense', id=r.id) }}" onsubmit="return confirm('Delete this record?');">
                  <button type="submit" class="btn btn-sm btn-outline-danger py-0 px-2"><i class="fa-solid fa-trash"></i></button>
                </form>
              </td>
            </tr>
            {% else %}
            <tr><td colspan="7" class="text-center py-5 text-muted">No expenses match your search.</td></tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
    """
    return render_page(
        content,
        title="Expenses",
        rows=rows,
        total_amount=total_amount,
        cats=CATEGORIES,
        keyword=keyword,
        selected_category=category
    )

@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "POST":
        t = request.form.get("title", "").strip()
        amt = float(request.form.get("amount", 0))
        cat = request.form.get("category")
        d = request.form.get("expense_date")
        pm = request.form.get("payment_method")
        desc = request.form.get("description", "").strip()

        if not t or amt <= 0 or not cat or not d or not pm:
            flash("Please fill in all required fields with valid details.", "danger")
        else:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    INSERT INTO expenses (user_id, title, amount, category, expense_date, payment_method, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (session["user_id"], t, amt, cat, d, pm, desc))
                conn.commit()
            flash("Expense logged successfully!", "success")
            return redirect(url_for("expenses"))

    content = """
    <div class="row justify-content-center">
      <div class="col-md-6">
        <div class="card shadow-sm p-4">
          <h4 class="fw-bold mb-3"><i class="fa-solid fa-plus-circle text-success me-2"></i>Record New Expense</h4>
          <form method="post">
            <div class="mb-3">
              <label class="form-label fw-semibold">Title <span class="text-danger">*</span></label>
              <input type="text" name="title" class="form-control" required placeholder="e.g. Milk & Groceries">
            </div>
            <div class="row mb-3">
              <div class="col">
                <label class="form-label fw-semibold">Amount (₹) <span class="text-danger">*</span></label>
                <input type="number" step="0.01" min="0.01" name="amount" class="form-control" required placeholder="100.00">
              </div>
              <div class="col">
                <label class="form-label fw-semibold">Date <span class="text-danger">*</span></label>
                <input type="date" name="expense_date" value="{{ today }}" class="form-control" required>
              </div>
            </div>
            <div class="row mb-3">
              <div class="col">
                <label class="form-label fw-semibold">Category <span class="text-danger">*</span></label>
                <select name="category" class="form-select" required>
                  {% for c in cats %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
                </select>
              </div>
              <div class="col">
                <label class="form-label fw-semibold">Payment Method <span class="text-danger">*</span></label>
                <select name="payment_method" class="form-select" required>
                  {% for p in pms %}<option value="{{ p }}">{{ p }}</option>{% endfor %}
                </select>
              </div>
            </div>
            <div class="mb-4">
              <label class="form-label fw-semibold">Notes / Description</label>
              <input type="text" name="description" class="form-control" placeholder="Optional notes">
            </div>
            <div class="d-flex justify-content-between">
              <a href="{{ url_for('expenses') }}" class="btn btn-outline-secondary">Cancel</a>
              <button type="submit" class="btn btn-success px-4">Save Expense</button>
            </div>
          </form>
        </div>
      </div>
    </div>
    """
    return render_page(
        content,
        title="Add Expense",
        cats=CATEGORIES,
        pms=PAYMENT_METHODS,
        today=date.today().isoformat()
    )

@app.route("/expenses/delete/<int:id>", methods=["POST"])
@login_required
def delete_expense(id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (id, session["user_id"]))
        conn.commit()
    flash("Expense record has been deleted.", "info")
    return redirect(url_for("expenses"))

@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    now = datetime.now()
    uid = session["user_id"]

    if request.method == "POST":
        month_param = request.form.get("month", f"{now.year}-{now.month:02d}")
        try:
            y, m = map(int, month_param.split("-"))
            amt = float(request.form.get("budget_amount", 0))
            if amt < 0:
                raise ValueError
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    INSERT INTO budgets (user_id, month, year, budget_amount)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, month, year)
                    DO UPDATE SET budget_amount = excluded.budget_amount
                """, (uid, m, y, amt))
                conn.commit()
            flash(f"Monthly budget saved for {month_param}: ₹{amt:,.2f}", "success")
        except (ValueError, TypeError):
            flash("Please enter a valid budget amount.", "danger")
        return redirect(url_for("budget", selected=month_param))

    selected_month = request.args.get("selected", f"{now.year}-{now.month:02d}")
    try:
        sel_y, sel_m = map(int, selected_month.split("-"))
    except ValueError:
        sel_y, sel_m = now.year, now.month
        selected_month = f"{sel_y}-{sel_m:02d}"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        b_row = conn.execute(
            "SELECT budget_amount FROM budgets WHERE user_id = ? AND month = ? AND year = ?",
            (uid, sel_m, sel_y)
        ).fetchone()

        spent = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS val FROM expenses WHERE user_id = ? AND expense_date LIKE ?",
            (uid, f"{selected_month}%")
        ).fetchone()["val"]

        history = conn.execute("""
            SELECT b.year, b.month, b.budget_amount,
                   COALESCE((SELECT SUM(amount) FROM expenses 
                             WHERE user_id = b.user_id 
                               AND strftime('%Y', expense_date) = printf('%04d', b.year)
                               AND strftime('%m', expense_date) = printf('%02d', b.month)), 0) as spent
            FROM budgets b
            WHERE b.user_id = ?
            ORDER BY b.year DESC, b.month DESC
        """, (uid,)).fetchall()

    budget_val = float(b_row["budget_amount"]) if b_row else 0.0
    spent_val = float(spent)
    rem = budget_val - spent_val if budget_val > 0 else 0.0
    util = round((spent_val / budget_val * 100), 1) if budget_val > 0 else 0.0

    content = """
    <div class="row g-4 mb-4">
      <div class="col-md-5">
        <div class="card shadow-sm p-4">
          <h4 class="fw-bold mb-3"><i class="fa-solid fa-sliders text-primary me-2"></i>Set Monthly Budget</h4>
          <form method="post">
            <div class="mb-3">
              <label class="form-label fw-semibold">Target Month</label>
              <input type="month" name="month" class="form-control" value="{{ selected_month }}" required>
            </div>
            <div class="mb-3">
              <label class="form-label fw-semibold">Budget Limit (₹)</label>
              <input type="number" step="0.01" min="0" name="budget_amount" class="form-control" value="{{ '%.2f'|format(budget_val) if budget_val > 0 else '' }}" required placeholder="e.g. 25000.00">
            </div>
            <button type="submit" class="btn btn-primary w-100 fw-semibold">Save Budget Limit</button>
          </form>
        </div>
      </div>

      <div class="col-md-7">
        <div class="card shadow-sm p-4 h-100">
          <h5 class="fw-bold mb-3">Status for {{ selected_month }}</h5>
          <div class="row g-3 mb-3 text-center">
            <div class="col-4 p-2 bg-light rounded"><div class="text-muted small">Budget</div><div class="fs-5 fw-bold">₹{{ "%.2f"|format(budget_val) }}</div></div>
            <div class="col-4 p-2 bg-light rounded"><div class="text-muted small">Spent</div><div class="fs-5 fw-bold text-danger">₹{{ "%.2f"|format(spent_val) }}</div></div>
            <div class="col-4 p-2 bg-light rounded"><div class="text-muted small">Remaining</div><div class="fs-5 fw-bold {{ 'text-success' if rem >= 0 else 'text-danger' }}">₹{{ "%.2f"|format(rem) }}</div></div>
          </div>
          {% if budget_val > 0 %}
          <div class="progress mb-2" style="height: 20px;">
            <div class="progress-bar {% if util > 100 %}bg-danger{% elif util >= 80 %}bg-warning text-dark{% else %}bg-success{% endif %}" style="width: {{ [util, 100]|min }}%;">{{ util }}%</div>
          </div>
          {% endif %}
        </div>
      </div>
    </div>
    """
    return render_page(
        content,
        title="Budgets",
        selected_month=selected_month,
        budget_val=budget_val,
        spent_val=spent_val,
        rem=rem,
        util=util,
        history=history
    )

@app.route("/analytics")
@login_required
def analytics():
    uid = session["user_id"]
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cats = conn.execute("""
            SELECT category, SUM(amount) AS val 
            FROM expenses 
            WHERE user_id = ? 
            GROUP BY category 
            ORDER BY val DESC
        """, (uid,)).fetchall()

        pms = conn.execute("""
            SELECT payment_method, SUM(amount) AS val 
            FROM expenses 
            WHERE user_id = ? 
            GROUP BY payment_method 
            ORDER BY val DESC
        """, (uid,)).fetchall()

    cat_labels = [r["category"] for r in cats]
    cat_values = [float(r["val"]) for r in cats]
    pm_labels = [r["payment_method"] for r in pms]
    pm_values = [float(r["val"]) for r in pms]

    content = """
    <h3 class="fw-bold mb-4"><i class="fa-solid fa-chart-line text-primary me-2"></i>Spending Analytics</h3>
    <div class="row g-4">
      <div class="col-lg-6">
        <div class="card shadow-sm p-4">
          <h5 class="fw-bold mb-3">Category-Wise Breakdown</h5>
          <div style="height: 300px;"><canvas id="catChart"></canvas></div>
        </div>
      </div>
      <div class="col-lg-6">
        <div class="card shadow-sm p-4">
          <h5 class="fw-bold mb-3">Payment Method Breakdown</h5>
          <div style="height: 300px;"><canvas id="pmChart"></canvas></div>
        </div>
      </div>
    </div>

    <script>
      const cLabels = {{ cat_labels|safe }};
      const cValues = {{ cat_values|safe }};
      new Chart(document.getElementById('catChart'), {
        type: 'doughnut',
        data: {
          labels: cLabels,
          datasets: [{ data: cValues, backgroundColor: ['#2563eb','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#06b6d4','#64748b'] }]
        },
        options: { responsive: true, maintainAspectRatio: false }
      });

      const pLabels = {{ pm_labels|safe }};
      const pValues = {{ pm_values|safe }};
      new Chart(document.getElementById('pmChart'), {
        type: 'polarArea',
        data: {
          labels: pLabels,
          datasets: [{ data: pValues, backgroundColor: ['#3b82f6','#10b981','#f97316','#6366f1','#e11d48','#14b8a6'] }]
        },
        options: { responsive: true, maintainAspectRatio: false }
      });
    </script>
    """
    return render_page(
        content,
        title="Analytics",
        cat_labels=json.dumps(cat_labels),
        cat_values=json.dumps(cat_values),
        pm_labels=json.dumps(pm_labels),
        pm_values=json.dumps(pm_values)
    )

@app.route("/export-csv")
@login_required
def export_csv():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT id, title, amount, category, expense_date, payment_method, description, created_at 
            FROM expenses 
            WHERE user_id = ? 
            ORDER BY expense_date DESC
        """, (session["user_id"],)).fetchall()

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["ID", "Title", "Amount (INR)", "Category", "Date", "Payment Method", "Description", "Created At"])
    for r in rows:
        w.writerow([r["id"], r["title"], f"{float(r['amount']):.2f}", r["category"], r["expense_date"], r["payment_method"], r["description"] or "", r["created_at"]])

    res = make_response(out.getvalue())
    res.headers["Content-Disposition"] = "attachment; filename=home_budget_report.csv"
    res.headers["Content-Type"] = "text/csv; charset=utf-8"
    return res

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)