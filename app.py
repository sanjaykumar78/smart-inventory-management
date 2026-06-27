from flask import Flask, render_template, request, flash, redirect, url_for, session
from flask_mail import Mail, Message
import joblib
import os
import pandas as pd
import math
import json
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask import jsonify, send_file, make_response
import csv
import io
import time
import random
from datetime import datetime
from db import get_db_connection
from db import get_db_connection

app = Flask(__name__)
print("TEST MAIL ROUTE LOADED")
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True

app.config['MAIL_USERNAME'] = 'sanjaykumarsak711@gmail.com'
app.config['MAIL_PASSWORD'] = 'qjml lknd xjra czub'

mail = Mail(app)
app.secret_key = "change-this-secret"

# Upload folder for profile pictures
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


class User(UserMixin):
    def __init__(self, username, role):
        self.id = username
        self.username = username
        self.role = role


def get_user_by_username(username: str):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        cur.close()
        return row
    except Exception as e:
        print("DB error get_user_by_username:", e)
        return None
    finally:
        if conn:
            conn.close()


def create_user(username: str, password_hash: str, full_name: str = '', email: str = '', theme: str = 'light', profile_picture: str = '', role: str = 'user'):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, full_name, email, password, theme, profile_picture, role) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (username, full_name, email, password_hash, theme, profile_picture, role)
        )
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        print("DB error create_user:", e)
        return False
    finally:
        if conn:
            conn.close()


def update_user_profile(username: str, full_name: str, email: str, profile_picture: str = None):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if profile_picture is not None:
            cur.execute("UPDATE users SET full_name=%s, email=%s, profile_picture=%s WHERE username=%s", (full_name, email, profile_picture, username))
        else:
            cur.execute("UPDATE users SET full_name=%s, email=%s WHERE username=%s", (full_name, email, username))
        conn.commit()
        cur.close()
    except Exception as e:
        print("DB error update_user_profile:", e)
    finally:
        if conn:
            conn.close()


def update_user_theme(username: str, theme: str):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET theme=%s WHERE username=%s", (theme, username))
        conn.commit()
        cur.close()
    except Exception as e:
        print("DB error update_user_theme:", e)
    finally:
        if conn:
            conn.close()


def update_user_password(username: str, password_hash: str):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET password=%s WHERE username=%s", (password_hash, username))
        conn.commit()
        cur.close()
    except Exception as e:
        print("DB error update_user_password:", e)
    finally:
        if conn:
            conn.close()


@login_manager.user_loader
def load_user(user_id):
    row = get_user_by_username(user_id)
    if row:
        return User(row.get('username'), 'user')
    return None

MODEL_PATH = "demand_prediction_model.pkl"

def load_model(path=MODEL_PATH):
    if not os.path.exists(path):
        print(f"Model file not found at '{path}'")
        return None
    try:
        model = joblib.load(path)
        print("Model loaded successfully")
        return model
    except Exception as e:
        print(f"Failed to load model: {e}")
        return None

model = load_model()

# --- Simple JSON product store ---
PRODUCTS_PATH = 'products.json'
INVENTORY_CONFIG_PATH = 'inventory_config.json'


def init_db():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                sku VARCHAR(100) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                category VARCHAR(100),
                region VARCHAR(100),
                inventory DECIMAL(10,2) DEFAULT 0,
                price DECIMAL(10,2) DEFAULT 0,
                reorder_level DECIMAL(10,2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                created_by VARCHAR(100)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS manager_notes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                note_text LONGTEXT,
                last_saved TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                action VARCHAR(100) NOT NULL,
                details VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inventory_notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                product_sku VARCHAR(100),
                title VARCHAR(255),
                severity VARCHAR(50),
                message VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reorder_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                product_sku VARCHAR(100),
                quantity INT DEFAULT 0,
                reason VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.close()
    except Exception as e:
        print("DB init error:", e)
    finally:
        if conn:
            conn.close()


def seed_sample_products():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM products")
        count = cur.fetchone()[0]
        if count == 0:
            cur.execute("""
                INSERT INTO products (sku, name, category, region, inventory, price, reorder_level) VALUES
                (%s, %s, %s, %s, %s, %s, %s),
                (%s, %s, %s, %s, %s, %s, %s),
                (%s, %s, %s, %s, %s, %s, %s)
            """, (
                'SKU-1001', 'Widget A', 'Electronics', 'North', 120, 25.5, 50,
                'SKU-1002', 'Widget B', 'Accessories', 'South', 15, 18.0, 20,
                'SKU-1003', 'Widget C', 'Electronics', 'West', 0, 40.0, 10
            ))
            conn.commit()
        cur.close()
    except Exception as e:
        print("Seed products error:", e)
    finally:
        if conn:
            conn.close()


init_db()
seed_sample_products()


def load_products():
    if not os.path.exists(PRODUCTS_PATH):
        return []
    try:
        with open(PRODUCTS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def save_products(products):
    with open(PRODUCTS_PATH, 'w', encoding='utf-8') as f:
        json.dump(products, f, indent=2)


def get_current_user_id():
    try:
        if getattr(current_user, 'is_authenticated', False):
            user_row = get_user_by_username(current_user.id)
            return user_row.get('id') if user_row else None
    except Exception:
        return None
    return None


def serialize_product(row):
    if not row:
        return None
    return {
        'id': row.get('id'),
        'sku': row.get('sku'),
        'name': row.get('name'),
        'category': row.get('category') or '',
        'region': row.get('region') or '',
        'inventory': float(row.get('inventory') or 0),
        'price': float(row.get('price') or 0),
        'reorder_level': float(row.get('reorder_level') or 0),
        'created_at': row.get('created_at'),
        'updated_at': row.get('updated_at')
    }


def compute_product_status(product):
    inventory = float(product.get('inventory') or 0)
    reorder_level = float(product.get('reorder_level') or 0)
    if inventory <= 0:
        return 'critical'
    if inventory <= reorder_level:
        return 'low'
    if inventory > reorder_level * 2:
        return 'over'
    return 'in'


def get_products_from_db(search='', category='', region='', status='', sort_by='name', sort_dir='asc'):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        query = 'SELECT * FROM products WHERE 1=1'
        params = []
        if search:
            like = f'%{search}%'
            query += ' AND (sku LIKE %s OR name LIKE %s OR category LIKE %s OR region LIKE %s)'
            params.extend([like, like, like, like])
        if category:
            query += ' AND category = %s'
            params.append(category)
        if region:
            query += ' AND region = %s'
            params.append(region)
        if status:
            if status == 'critical':
                query += ' AND inventory <= 0'
            elif status == 'low':
                query += ' AND inventory <= reorder_level'
            elif status == 'over':
                query += ' AND inventory > reorder_level * 2'
            else:
                query += ' AND inventory > 0 AND inventory > reorder_level'
        order_field = 'name'
        if sort_by in {'price', 'inventory', 'reorder_level', 'category', 'region', 'sku'}:
            order_field = sort_by
        direction = 'ASC' if sort_dir != 'desc' else 'DESC'
        query += f' ORDER BY {order_field} {direction}'
        cur.execute(query, params)
        rows = cur.fetchall()
        return [serialize_product(row) for row in rows]
    except Exception as e:
        print('DB get_products error:', e)
        return []
    finally:
        if conn:
            conn.close()


def build_inventory_summary(products):
    total_products = len(products)
    total_inventory = sum(float(p.get('inventory') or 0) for p in products)
    inventory_value = sum((float(p.get('inventory') or 0) * float(p.get('price') or 0)) for p in products)
    low_stock = sum(1 for p in products if float(p.get('inventory') or 0) <= float(p.get('reorder_level') or 0))
    out_of_stock = sum(1 for p in products if float(p.get('inventory') or 0) <= 0)
    average_stock = round(total_inventory / total_products, 2) if total_products else 0
    stock_health = round(max(0, min(100, 100 - (low_stock / total_products * 50) - (out_of_stock / total_products * 30) + (average_stock / max(1, total_inventory or 1) * 10)))) if total_products else 100
    return {
        'total_products': total_products,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'inventory_value': round(inventory_value, 2),
        'average_stock': average_stock,
        'stock_health': stock_health,
    }


def build_ai_recommendations(products):
    recommendations = []
    if not products:
        return ['No product data available. Add inventory to generate recommendations.']
    for product in products:
        inventory = float(product.get('inventory') or 0)
        reorder_level = float(product.get('reorder_level') or 0)
        if inventory <= reorder_level:
            recommendations.append(f"Increase stock for {product['name']} by {max(1, int(reorder_level - inventory + 10))} units.")
        elif inventory > reorder_level * 2:
            recommendations.append(f"Reduce stock for {product['name']} by {max(1, int(inventory - reorder_level * 2))} units.")
    if not recommendations:
        recommendations.append('Inventory looks balanced. No urgent actions needed.')
    category_counts = {}
    for product in products:
        category_counts[product.get('category') or 'Uncategorized'] = category_counts.get(product.get('category') or 'Uncategorized', 0) + 1
    if category_counts:
        top_category = max(category_counts.items(), key=lambda item: item[1])[0]
        recommendations.append(f"Highest selling category: {top_category}.")
    return recommendations[:6]


def sync_inventory_notifications(products):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM inventory_notifications')
        for product in products:
            inventory = float(product.get('inventory') or 0)
            reorder_level = float(product.get('reorder_level') or 0)
            if inventory <= 0:
                cur.execute('INSERT INTO inventory_notifications (product_sku, title, severity, message) VALUES (%s, %s, %s, %s)', (product.get('sku'), 'Out of Stock', 'danger', f"{product.get('name')} is out of stock."))
            elif inventory <= reorder_level:
                cur.execute('INSERT INTO inventory_notifications (product_sku, title, severity, message) VALUES (%s, %s, %s, %s)', (product.get('sku'), 'Low Stock', 'warning', f"{product.get('name')} is below reorder level."))
            elif inventory > reorder_level * 2:
                cur.execute('INSERT INTO inventory_notifications (product_sku, title, severity, message) VALUES (%s, %s, %s, %s)', (product.get('sku'), 'High Inventory', 'info', f"{product.get('name')} has high inventory."))
        conn.commit()
        cur.close()
    except Exception as e:
        print('Notification sync error:', e)
    finally:
        if conn:
            conn.close()


def log_activity(action, details='', user_id=None):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('INSERT INTO activity_logs (user_id, action, details) VALUES (%s, %s, %s)', (user_id, action, details))
        conn.commit()
        cur.close()
    except Exception as e:
        print('Activity log error:', e)
    finally:
        if conn:
            conn.close()


def get_recent_activity(limit=10):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT action, details, created_at FROM activity_logs ORDER BY created_at DESC LIMIT %s', (limit,))
        rows = cur.fetchall()
        return rows
    except Exception as e:
        print('Recent activity error:', e)
        return []
    finally:
        if conn:
            conn.close()


def build_chart_data(products):
    category_map = {}
    region_map = {}
    for product in products:
        category = product.get('category') or 'Uncategorized'
        region = product.get('region') or 'Unassigned'
        category_map[category] = category_map.get(category, 0) + float(product.get('inventory') or 0)
        region_map[region] = region_map.get(region, 0) + float(product.get('inventory') or 0)
    return {
        'category_labels': list(category_map.keys()),
        'category_values': [round(v, 2) for v in category_map.values()],
        'region_labels': list(region_map.keys()),
        'region_values': [round(v, 2) for v in region_map.values()],
        'trend_labels': ['Current', 'Low', 'Critical'],
        'trend_values': [max(0, len(products) - 1), sum(1 for p in products if float(p.get('inventory') or 0) <= float(p.get('reorder_level') or 0)), sum(1 for p in products if float(p.get('inventory') or 0) <= 0)]
    }


def build_pdf_report(products, summary):
    buffer = io.BytesIO()
    lines = [
        'Inventory Report',
        '================',
        f"Total Products: {summary.get('total_products', 0)}",
        f"Low Stock: {summary.get('low_stock', 0)}",
        f"Out of Stock: {summary.get('out_of_stock', 0)}",
        f"Inventory Value: ${summary.get('inventory_value', 0):,.2f}",
        f"Average Stock: {summary.get('average_stock', 0)}",
        f"Stock Health: {summary.get('stock_health', 0)}%",
        '',
        'Products:'
    ]
    for product in products:
        lines.append(f"- {product.get('sku')} | {product.get('name')} | Stock: {product.get('inventory')} | Reorder: {product.get('reorder_level')}")
    content = '\n'.join(lines).encode('latin-1', 'replace')
    buffer.write(content)
    buffer.seek(0)
    return buffer


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        try:
            inventory_level = float(request.form.get("inventory_level", 0))
            units_sold = float(request.form.get("units_sold", 0))
            units_ordered = float(request.form.get("units_ordered", 0))
            price = float(request.form.get("price", 0))
            discount = float(request.form.get("discount", 0))
            competitor_pricing = float(request.form.get("competitor_pricing", 0))

            # Prepare features for the model. Column names/order must match the trained model's expectation.
            features = pd.DataFrame([
                {
                    "inventory_level": inventory_level,
                    "units_sold": units_sold,
                    "units_ordered": units_ordered,
                    "price": price,
                    "discount": discount,
                    "competitor_pricing": competitor_pricing,
                }
            ])

            if model is None:
                flash(f"Model not found at '{MODEL_PATH}'. Place your model file there.", "danger")
                return render_template("index.html")

            pred = model.predict(features)
            predicted_demand = float(pred[0])
            if math.isnan(predicted_demand):
                raise ValueError("Model returned NaN")

            predicted_demand = max(0.0, predicted_demand)
            predicted_int = int(round(predicted_demand))

            # Simple safety stock and reorder calculation
            safety_stock = max(1, int(math.ceil(0.2 * predicted_demand)))
            reorder_quantity = max(0, predicted_int + safety_stock - int(inventory_level))

            # Stockout risk as percentage when inventory < predicted demand
            if inventory_level >= predicted_demand:
                stockout_risk = 0.0
            else:
                stockout_risk = min(100.0, (predicted_demand - inventory_level) / (predicted_demand + 1e-9) * 100)

            return render_template(
                "result.html",
                predicted_demand=predicted_int,
                reorder_quantity=reorder_quantity,
                stockout_risk=round(stockout_risk, 1),
                inputs={
                    "inventory_level": inventory_level,
                    "units_sold": units_sold,
                    "units_ordered": units_ordered,
                    "price": price,
                    "discount": discount,
                    "competitor_pricing": competitor_pricing,
                },
            )

        except Exception as e:
            flash(str(e), "danger")
            return render_template("index.html")

    return render_template("index.html")


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'user')

        if not username or not password:
            flash('Provide username and password', 'danger')
            return render_template('register.html')

        # check existing user in DB
        existing = get_user_by_username(username)
        if existing:
            flash('Username already exists', 'danger')
            return render_template('register.html')

        password_hash = generate_password_hash(password)
        created = create_user(username, password_hash, role=role, full_name='', email='', theme='light', profile_picture='')
        if not created:
            flash('Registration failed', 'danger')
            return render_template('register.html')
        user = User(username, role)
        login_user(user)
        # initialize session defaults
        session.setdefault('user_settings', {})['profile_picture'] = ''
        session.setdefault('user_settings', {})['full_name'] = ''
        session.setdefault('user_settings', {})['email'] = ''
        session['theme'] = 'light'
        flash('Registered and logged in', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user_row = get_user_by_username(username)
        print("DB USER:", user_row)
        if not user_row or not check_password_hash(user_row.get('password', ''), password):
            flash('Invalid credentials', 'danger')
            return render_template('login.html')

        user = User(username, 'user')
        login_user(user)
        # restore persisted user settings (profile picture, theme, etc.) into session
        try:
            urec = user_row or {}
            session.setdefault('user_settings', {})['profile_picture'] = urec.get('profile_picture', session.get('user_settings', {}).get('profile_picture', ''))
            session.setdefault('user_settings', {})['full_name'] = urec.get('full_name', session.get('user_settings', {}).get('full_name', ''))
            session.setdefault('user_settings', {})['email'] = urec.get('email', session.get('user_settings', {}).get('email', ''))
            # restore theme
            session['theme'] = urec.get('theme', session.get('theme', session.get('user_settings', {}).get('theme', 'light')))
            print("Current session theme:", session.get('theme'))
        except Exception:
            pass
        flash('Logged in', 'success')
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/products')
@login_required
def products():
    products = get_products_from_db()
    summary = build_inventory_summary(products)
    recommendations = build_ai_recommendations(products)
    chart_data = build_chart_data(products)
    activity = get_recent_activity(10)
    return render_template('products.html', products=products, kpis=summary, ai_recommendations=recommendations, chart_data=chart_data, activity=activity)


@app.route('/products/add', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        sku = request.form.get('sku') or f"SKU-{int(pd.Timestamp.now().timestamp())}"
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip()
        region = request.form.get('region', '').strip()
        inventory = float(request.form.get('inventory', 0) or 0)
        price = float(request.form.get('price', 0) or 0)
        reorder_level = float(request.form.get('reorder_level', 0) or 0)
        if not name:
            return jsonify({'success': False, 'message': 'Name is required'}), 400
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('INSERT INTO products (sku, name, category, region, inventory, price, reorder_level, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)', (sku, name, category, region, inventory, price, reorder_level, current_user.id))
            conn.commit()
            cur.close()
            log_activity('Product Added', f'{name} ({sku})', get_current_user_id())
            sync_inventory_notifications(get_products_from_db())
            return jsonify({'success': True, 'message': 'Product added', 'product': serialize_product({'id': None, 'sku': sku, 'name': name, 'category': category, 'region': region, 'inventory': inventory, 'price': price, 'reorder_level': reorder_level})})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400
        finally:
            if conn:
                conn.close()

    return render_template('add_product.html')


@app.route('/products/edit/<sku>', methods=['GET', 'POST'])
@login_required
def edit_product(sku):
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip()
        region = request.form.get('region', '').strip()
        inventory = float(request.form.get('inventory', 0) or 0)
        price = float(request.form.get('price', 0) or 0)
        reorder_level = float(request.form.get('reorder_level', 0) or 0)
        if not name:
            return jsonify({'success': False, 'message': 'Name is required'}), 400
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('UPDATE products SET name=%s, category=%s, region=%s, inventory=%s, price=%s, reorder_level=%s WHERE sku=%s', (name, category, region, inventory, price, reorder_level, sku))
            conn.commit()
            cur.close()
            log_activity('Product Edited', f'{name} ({sku})', get_current_user_id())
            sync_inventory_notifications(get_products_from_db())
            return jsonify({'success': True, 'message': 'Product updated'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400
        finally:
            if conn:
                conn.close()

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT * FROM products WHERE sku=%s', (sku,))
        prod = cur.fetchone()
        cur.close()
        return render_template('edit_product.html', product=serialize_product(prod))
    except Exception as e:
        flash(str(e), 'danger')
        return redirect(url_for('products'))
    finally:
        if conn:
            conn.close()


@app.route('/products/delete/<sku>', methods=['POST'])
@login_required
def delete_product(sku):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM products WHERE sku=%s', (sku,))
        conn.commit()
        cur.close()
        log_activity('Product Deleted', sku, get_current_user_id())
        sync_inventory_notifications(get_products_from_db())
        return jsonify({'success': True, 'message': 'Product deleted'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        if conn:
            conn.close()


@app.route('/export/products')
@login_required
def export_products():
    products = get_products_from_db()
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(['sku','name','category','region','inventory','price','reorder_level'])
    for p in products:
        writer.writerow([p.get('sku'), p.get('name'), p.get('category'), p.get('region'), p.get('inventory'), p.get('price'), p.get('reorder_level')])
    mem = io.BytesIO()
    mem.write(si.getvalue().encode('utf-8'))
    mem.seek(0)
    log_activity('Export', 'Inventory CSV exported', get_current_user_id())
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name='products.csv')


@app.route('/api/products', methods=['GET'])
@login_required
def api_products():
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    region = request.args.get('region', '')
    status = request.args.get('status', '')
    sort_by = request.args.get('sort_by', 'name')
    sort_dir = request.args.get('sort_dir', 'asc')
    products = get_products_from_db(search=search, category=category, region=region, status=status, sort_by=sort_by, sort_dir=sort_dir)
    summary = build_inventory_summary(products)
    return jsonify({'products': products, 'summary': summary, 'chart': build_chart_data(products), 'recommendations': build_ai_recommendations(products), 'activity': get_recent_activity(10)})


@app.route('/api/products/<sku>', methods=['PUT'])
@login_required
def api_update_product(sku):
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Name is required'}), 400
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('UPDATE products SET name=%s, category=%s, region=%s, inventory=%s, price=%s, reorder_level=%s WHERE sku=%s', (
            name, data.get('category',''), data.get('region',''), data.get('inventory',0), data.get('price',0), data.get('reorder_level',0), sku
        ))
        conn.commit()
        cur.close()
        log_activity('Product Edited', f'{name} ({sku})', get_current_user_id())
        sync_inventory_notifications(get_products_from_db())
        return jsonify({'success': True, 'message': 'Product updated'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        if conn:
            conn.close()


@app.route('/api/products/bulk', methods=['POST'])
@login_required
def api_bulk_products():
    data = request.get_json() or {}
    skus = data.get('skus') or []
    action = data.get('action')
    if not skus:
        return jsonify({'success': False, 'message': 'No products selected'}), 400
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if action == 'delete':
            cur.executemany('DELETE FROM products WHERE sku=%s', [(sku,) for sku in skus])
            log_activity('Bulk Delete', ','.join(skus), get_current_user_id())
        elif action == 'category':
            cur.execute('UPDATE products SET category=%s WHERE sku IN %s', (data.get('value'), tuple(skus)))
            log_activity('Bulk Update', f'Category -> {data.get("value")}', get_current_user_id())
        elif action == 'region':
            cur.execute('UPDATE products SET region=%s WHERE sku IN %s', (data.get('value'), tuple(skus)))
            log_activity('Bulk Update', f'Region -> {data.get("value")}', get_current_user_id())
        elif action == 'reorder':
            cur.execute('UPDATE products SET reorder_level=%s WHERE sku IN %s', (data.get('value'), tuple(skus)))
            log_activity('Bulk Update', f'Reorder Level -> {data.get("value")}', get_current_user_id())
        elif action == 'stock':
            amount = float(data.get('value') or 0)
            for sku in skus:
                cur.execute('SELECT inventory FROM products WHERE sku=%s', (sku,))
                row = cur.fetchone()
                if row:
                    cur.execute('UPDATE products SET inventory=%s WHERE sku=%s', (float(row[0]) + amount, sku))
            log_activity('Bulk Update', f'Stock adjusted by {amount}', get_current_user_id())
        conn.commit()
        cur.close()
        sync_inventory_notifications(get_products_from_db())
        return jsonify({'success': True, 'message': 'Bulk operation completed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        if conn:
            conn.close()


@app.route('/api/products/notes', methods=['GET', 'POST'])
@login_required
def api_notes():
    user_id = get_current_user_id()
    if request.method == 'POST':
        note_text = request.get_json().get('note_text', '') if request.get_json() else ''
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('SELECT id FROM manager_notes WHERE user_id=%s', (user_id,))
            row = cur.fetchone()
            if row:
                cur.execute('UPDATE manager_notes SET note_text=%s, last_saved=NOW() WHERE user_id=%s', (note_text, user_id))
            else:
                cur.execute('INSERT INTO manager_notes (user_id, note_text) VALUES (%s, %s)', (user_id, note_text))
            conn.commit()
            cur.close()
            return jsonify({'success': True, 'message': 'Notes saved'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400
        finally:
            if conn:
                conn.close()
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute('SELECT note_text, last_saved FROM manager_notes WHERE user_id=%s', (user_id,))
        row = cur.fetchone()
        cur.close()
        return jsonify({'note_text': row.get('note_text') if row else '', 'last_saved': row.get('last_saved') if row else None})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        if conn:
            conn.close()


@app.route('/api/products/report')
@login_required
def api_report():
    products = get_products_from_db()
    summary = build_inventory_summary(products)
    buffer = build_pdf_report(products, summary)
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=inventory_report.pdf'
    log_activity('Report', 'PDF report generated', get_current_user_id())
    return response


@app.route('/api/products/reorder', methods=['POST'])
@login_required
def api_reorder():
    data = request.get_json() or {}
    skus = data.get('skus') or []
    if not skus:
        return jsonify({'success': False, 'message': 'No products selected'}), 400
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for sku in skus:
            cur.execute('SELECT inventory, reorder_level FROM products WHERE sku=%s', (sku,))
            row = cur.fetchone()
            if row:
                inventory = float(row[0] or 0)
                reorder_level = float(row[1] or 0)
                quantity = max(1, int(reorder_level - inventory + 10))
                cur.execute('UPDATE products SET reorder_level=%s WHERE sku=%s', (max(reorder_level, inventory + quantity), sku))
                cur.execute('INSERT INTO reorder_history (product_sku, quantity, reason) VALUES (%s, %s, %s)', (sku, quantity, 'reorder'))
        conn.commit()
        cur.close()
        log_activity('Reorder', ','.join(skus), get_current_user_id())
        return jsonify({'success': True, 'message': 'Reorder action completed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        if conn:
            conn.close()


@app.route('/api/products/smart-reorder', methods=['GET', 'POST'])
@login_required
def api_smart_reorder():
    products = get_products_from_db()
    suggestions = []
    for product in products:
        inventory = float(product.get('inventory') or 0)
        reorder_level = float(product.get('reorder_level') or 0)
        if inventory <= reorder_level:
            suggested = max(10, int((reorder_level - inventory) * 2 + 10))
            suggestions.append({'sku': product['sku'], 'name': product['name'], 'suggested_quantity': suggested})
    return jsonify({'success': True, 'suggestions': suggestions})


@app.route('/api/predict', methods=['POST'])
@login_required
def api_predict():
    data = request.get_json() or {}
    try:
        features = pd.DataFrame([{
            'inventory_level': float(data.get('inventory_level', 0)),
            'units_sold': float(data.get('units_sold', 0)),
            'units_ordered': float(data.get('units_ordered', 0)),
            'price': float(data.get('price', 0)),
            'discount': float(data.get('discount', 0)),
            'competitor_pricing': float(data.get('competitor_pricing', 0)),
        }])
    except Exception as e:
        return jsonify({'error': 'Invalid input', 'detail': str(e)}), 400

    if model is None:
        return jsonify({'error': 'Model not loaded'}), 500

    try:
        pred = model.predict(features)
        predicted = float(max(0, pred[0]))
        predicted_int = int(round(predicted))
        safety_stock = max(1, int(math.ceil(0.2 * predicted)))
        inventory_level = float(data.get('inventory_level', 0))
        reorder_quantity = max(0, predicted_int + safety_stock - int(inventory_level))
        if inventory_level >= predicted:
            stockout_risk = 0.0
        else:
            stockout_risk = min(100.0, (predicted - inventory_level) / (predicted + 1e-9) * 100)

        return jsonify({'predicted_demand': predicted_int, 'reorder_quantity': reorder_quantity, 'stockout_risk': round(stockout_risk,1)})
    except Exception as e:
        return jsonify({'error': 'Prediction failed', 'detail': str(e)}), 500


@app.route('/ai-insights')
@login_required
def ai_insights():
    products = get_products_from_db()
    insights = build_ai_recommendations(products)
    return render_template('ai_insights.html', insights=insights)


@app.route('/reports')
@login_required
def reports():
    # Sample reports page with charts; pull data from products if available
    products = load_products()
    if products:
        # monthly sample derived from product inventory changes (placeholder)
        labels = ['Jan','Feb','Mar','Apr','May','Jun']
        sales = [sum(int(p.get('inventory',0)) for p in products) // 10 for _ in labels]
        dist = {}
        for p in products:
            cat = p.get('category') or 'Uncategorized'
            dist[cat] = dist.get(cat, 0) + p.get('inventory', 0)
        dist_labels = list(dist.keys())
        dist_values = list(dist.values())
    else:
        labels = ['Jan','Feb','Mar','Apr','May','Jun']
        sales = [120,140,160,130,180,210]
        dist_labels = ['Mobiles','Laptops','Accessories','Tablets']
        dist_values = [40,25,20,15]

    return render_template('reports.html', active_page='/reports', chart={'labels': labels, 'sales': sales}, dist_labels=dist_labels, dist_values=dist_values)


@app.route('/inventory-configuration', methods=['GET', 'POST'])
@login_required
def inventory_configuration():
    # Load or initialize configuration
    default_config = {
        'low_stock_threshold': 10,
        'critical_stock_threshold': 3,
        'default_reorder_quantity': 50,
        'forecast_period_months': 6,
        'forecast_frequency': 'weekly',
        'model_status': 'Loaded' if model is not None else 'Missing',
        'alert_low_stock': True,
        'alert_reorder_suggestions': True,
        'alert_demand_spike': True,
        'currency': 'USD',
        'warehouse_location': '',
        'default_category': ''
    }

    config = default_config.copy()
    if os.path.exists(INVENTORY_CONFIG_PATH):
        try:
            with open(INVENTORY_CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                config.update(cfg)
        except Exception:
            pass

    if request.method == 'POST':
        # Read form fields and save
        try:
            config['low_stock_threshold'] = int(request.form.get('low_stock_threshold', config['low_stock_threshold']))
            config['critical_stock_threshold'] = int(request.form.get('critical_stock_threshold', config['critical_stock_threshold']))
            config['default_reorder_quantity'] = int(request.form.get('default_reorder_quantity', config['default_reorder_quantity']))
            config['forecast_period_months'] = int(request.form.get('forecast_period_months', config['forecast_period_months']))
            config['forecast_frequency'] = request.form.get('forecast_frequency', config['forecast_frequency'])
            # model_status is informational
            config['alert_low_stock'] = bool(request.form.get('alert_low_stock'))
            config['alert_reorder_suggestions'] = bool(request.form.get('alert_reorder_suggestions'))
            config['alert_demand_spike'] = bool(request.form.get('alert_demand_spike'))
            config['currency'] = request.form.get('currency', config['currency'])
            config['warehouse_location'] = request.form.get('warehouse_location', config['warehouse_location'])
            config['default_category'] = request.form.get('default_category', config['default_category'])

            with open(INVENTORY_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            flash('Inventory configuration saved', 'success')
            return redirect(url_for('inventory_configuration'))
        except Exception as e:
            flash(f'Failed to save configuration: {e}', 'danger')

    return render_template('inventory_configuration.html', active_page='/inventory-configuration', config=config)


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    # Defaults pulled from session or current_user
    # try to source persisted user profile values from users.json if session doesn't have them
    persisted_row = get_user_by_username(current_user.id) or {}
    persisted = {
        'profile_picture': persisted_row.get('profile_picture', '') if persisted_row else '',
        'full_name': persisted_row.get('full_name', '') if persisted_row else '',
        'email': persisted_row.get('email', '') if persisted_row else '',
        'theme': persisted_row.get('theme', 'light') if persisted_row else 'light'
    }
    defaults = {
        'profile_picture': session.get('user_settings', {}).get('profile_picture', '') or persisted.get('profile_picture', ''),
        'username': current_user.id,
        'full_name': session.get('user_settings', {}).get('full_name', '') or persisted.get('full_name', ''),
        'email': session.get('user_settings', {}).get('email', '') or persisted.get('email', ''),
        'role': getattr(current_user, 'role', 'user'),
        'theme': session.get('theme', None) or session.get('user_settings', {}).get('theme', '') or persisted.get('theme', 'light'),
    }

    if request.method == 'POST':
        form_name = request.form.get('form_name')

        # debug logs requested by user
        print("FORM NAME:", form_name)
        print("REQUEST FILES:", request.files)
        if 'profile_picture' in request.files:
            print("PROFILE PICTURE FOUND")
        else:
            print("PROFILE PICTURE NOT FOUND")

        # PROFILE form
        if form_name == 'profile':
            print("PROFILE UPDATE BLOCK EXECUTED")
            # upload validation
            uploaded_file = request.files.get('profile_picture')
            if uploaded_file:
                print("FILENAME:", uploaded_file.filename)
            else:
                print("No uploaded file object for 'profile_picture'")

            if uploaded_file and getattr(uploaded_file, 'filename', None):
                upload_dir = os.path.join(app.static_folder, 'uploads')
                os.makedirs(upload_dir, exist_ok=True)
                filename = secure_filename(uploaded_file.filename)
                save_path = os.path.join(upload_dir, filename)
                uploaded_file.save(save_path)
                print("SAVED:", save_path)

                # persist filename to defaults, session and DB
                defaults['profile_picture'] = filename
                session.setdefault('user_settings', {})['profile_picture'] = filename
                try:
                    update_user_profile(current_user.id, defaults.get('full_name', ''), defaults.get('email', ''), profile_picture=filename)
                except Exception as e:
                    print("Failed to persist profile_picture:", e)

                flash('Profile picture uploaded successfully', 'success')

            # basic validation
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()
            if not full_name or not email:
                flash('Full name and email are required.', 'danger')
                return redirect(url_for('settings'))
            defaults['full_name'] = full_name
            defaults['email'] = email
            # save to session
            session.setdefault('user_settings', {}).update({
                'profile_picture': defaults['profile_picture'],
                'full_name': defaults['full_name'],
                'email': defaults['email']
            })
            # persist to DB so settings survive logout/login
            try:
                update_user_profile(current_user.id, defaults['full_name'], defaults['email'], profile_picture=defaults['profile_picture'])
            except Exception:
                pass
            flash('Profile updated.', 'success')
            return redirect(url_for('settings'))

        # APPEARANCE form
        if form_name == 'appearance':
            theme = request.form.get('theme', 'light')
            # Save theme to session and persist to user record
            session['theme'] = theme
            session.setdefault('user_settings', {})['theme'] = theme
            print("Theme selected:", theme)
            print("Current session theme:", session.get('theme'))
            try:
                update_user_theme(current_user.id, theme)
            except Exception:
                pass
            flash('Theme saved.', 'success')
            return redirect(url_for('settings'))

        # SECURITY form
        if form_name == 'security':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')
            if not current_pw or not new_pw or not confirm_pw:
                flash('All password fields are required.', 'danger')
                return redirect(url_for('settings'))
            user_row = get_user_by_username(current_user.id)
            print("DB USER:", user_row)
            if not user_row or not check_password_hash(user_row.get('password', ''), current_pw):
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for('settings'))
            if new_pw != confirm_pw:
                flash('New passwords do not match.', 'danger')
                return redirect(url_for('settings'))
            update_user_password(current_user.id, generate_password_hash(new_pw))
            flash('Password updated successfully.', 'success')
            return redirect(url_for('settings'))

    # GET: render template
    return render_template('settings.html', active_page='/settings', settings=defaults)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    # Sample data for the dashboard - replace with real data from DB in future
    kpis = {
        'total_products': 1248,
        'inventory_level': '42,380',
        'predicted_demand': '5,120',
        'stockout_risk': 4.6,
    }

    chart = {
        'labels': ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
        'demand': [420,480,500,520,600,700,680,720,760,800,820,900],
        'inventory': [600,580,560,540,520,500,480,460,440,420,400,380]
    }

    recent_inventory = [
        {'sku':'SKU-1001','name':'Widget A','inventory':120,'demand':80,'reorder':40},
        {'sku':'SKU-1002','name':'Widget B','inventory':60,'demand':90,'reorder':50},
        {'sku':'SKU-1003','name':'Gadget C','inventory':20,'demand':50,'reorder':40},
    ]

    ai_recommendations = [
        'Increase reorder for SKU-1002 by 50 units.',
        'Review pricing for Widget B to improve margin.',
        'Flag SKU-1003 for promotional activity to reduce stockout risk.'
    ]

    # compute inventory metrics from products if available
    products = load_products()
    if products:
        total_products = len(products)
        inventory_value = sum([p.get('inventory',0) * p.get('price',0) for p in products])
        total_inventory = sum([p.get('inventory',0) for p in products])
        # build distribution
        dist = {}
        for p in products:
            cat = p.get('category') or 'Uncategorized'
            dist[cat] = dist.get(cat,0) + p.get('inventory',0)
        dist_labels = list(dist.keys())
        dist_values = list(dist.values())
    else:
        total_products = kpis['total_products']
        inventory_value = 42380
        total_inventory = 42380
        dist_labels = ['Widgets','Gadgets','Misc']
        dist_values = [20000,15000,7380]

    # update KPIs
    kpis['total_products'] = total_products
    kpis['inventory_value'] = f"${inventory_value:,.0f}"
    kpis['inventory_level'] = f"{total_inventory:,}"

    if getattr(current_user, 'role', 'user') == 'admin':
        # compute alerts from products
        alerts = []
        for p in products:
            try:
                inv = float(p.get('inventory', 0))
                reorder_level = float(p.get('reorder_level', 0))
            except Exception:
                inv = 0
                reorder_level = 0
            if inv <= reorder_level:
                alerts.append({'sku': p.get('sku'), 'name': p.get('name'), 'risk': 'High'})

        return render_template('dashboard.html', kpis=kpis, chart=chart, recent_inventory=recent_inventory, ai_recommendations=ai_recommendations, alerts=alerts, dist_labels=dist_labels, dist_values=dist_values)

    # For non-admin users, show the lighter user dashboard
    # for non-admin users supply user-specific KPIs and charts
    user_kpis = {
        'total_products': kpis['total_products'],
        'inventory_value': kpis['inventory_value'],
        'predicted_demand': kpis['predicted_demand'],
        'low_stock_alerts': len([p for p in products if p.get('inventory',0) <= p.get('reorder_level',0)]) if products else 0
    }
    return render_template('user_dashboard.html', kpis=user_kpis, chart=chart, recent_inventory=recent_inventory, ai_recommendations=ai_recommendations, dist_labels=dist_labels, dist_values=dist_values)

@app.route('/test-mail')
def test_mail():
    try:
        msg = Message(
            subject="Smart Inventory Test",
            sender=app.config['MAIL_USERNAME'],
            recipients=["sanjaykumarsak711@gmail.com"]
        )

        msg.body = "Congratulations! Flask-Mail is working successfully."

        mail.send(msg)

        return "Email sent successfully!"

    except Exception as e:
        return f"Error sending email: {str(e)}"
    
print("SEND OTP ROUTE LOADED")

@app.route('/send-otp', methods=['POST'])
def send_otp():
    try:
        email = request.form.get('email')

        otp = str(random.randint(100000, 999999))

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO password_otps (email, otp) VALUES (%s, %s)",
            (email, otp)
        )

        conn.commit()

        msg = Message(
            subject="Smart Inventory Password Reset OTP",
            sender=app.config['MAIL_USERNAME'],
            recipients=[email]
        )

        msg.body = f"""
Your OTP for Smart Inventory password reset is:

{otp}

Do not share this OTP with anyone.
"""

        mail.send(msg)

        cur.close()
        conn.close()

        return "OTP Sent Successfully"

    except Exception as e:
        return f"Error: {str(e)}"
    
@app.route('/verify-otp', methods=['POST'])
def verify_otp():
    try:
        email = request.form.get('email')
        otp = request.form.get('otp')

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)

        cur.execute(
            """
            SELECT otp
            FROM password_otps
            WHERE email=%s
            ORDER BY id DESC
            LIMIT 1
            """,
            (email,)
        )

        row = cur.fetchone()

        cur.close()
        conn.close()

        if row and row['otp'] == otp:
            return "VALID"

        return "INVALID OTP"

    except Exception as e:
        return f"Error: {str(e)}"
    
@app.route('/reset-password', methods=['POST'])
def reset_password():
    try:
        email = request.form.get('email')
        new_password = request.form.get('new_password')

        hashed_password = generate_password_hash(new_password)

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "UPDATE users SET password=%s WHERE email=%s",
            (hashed_password, email)
        )

        conn.commit()

        cur.close()
        conn.close()

        return "Password Updated Successfully"

    except Exception as e:
        return f"Error: {str(e)}"

print("BOTTOM OF FILE REACHED")

if __name__ == "__main__":
    print("STARTING FLASK SERVER")
    app.run(debug=True, host="0.0.0.0", port=5000)
