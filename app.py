from flask import Flask, render_template, request, flash, redirect, url_for, session
import joblib
import os
import pandas as pd
import math
import json
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask import jsonify, send_file
import csv
import io

app = Flask(__name__)
app.secret_key = "change-this-secret"

# Upload folder for profile pictures
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Simple file-based user store for scaffolded auth ---
USERS_PATH = "users.json"

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


class User(UserMixin):
    def __init__(self, username, role):
        self.id = username
        self.username = username
        self.role = role


def load_users():
    if not os.path.exists(USERS_PATH):
        return {}
    try:
        with open(USERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_users(users: dict):
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


@login_manager.user_loader
def load_user(user_id):
    users = load_users()
    if user_id in users:
        return User(user_id, users[user_id].get("role", "user"))
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

        users = load_users()
        if username in users:
            flash('Username already exists', 'danger')
            return render_template('register.html')

        users[username] = {
            'password_hash': generate_password_hash(password),
            'role': role,
        }
        save_users(users)
        user = User(username, role)
        login_user(user)
        flash('Registered and logged in', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        users = load_users()
        user_record = users.get(username)
        if not user_record or not check_password_hash(user_record.get('password_hash', ''), password):
            flash('Invalid credentials', 'danger')
            return render_template('login.html')

        user = User(username, user_record.get('role', 'user'))
        login_user(user)
        flash('Logged in', 'success')
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/products')
@login_required
def products():
    products = load_products()
    return render_template('products.html', products=products)


@app.route('/products/add', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        sku = request.form.get('sku') or f"SKU-{int(pd.Timestamp.now().timestamp())}"
        name = request.form.get('name')
        category = request.form.get('category')
        region = request.form.get('region')
        inventory = request.form.get('inventory', 0)
        price = request.form.get('price', 0)
        reorder_level = request.form.get('reorder_level', 0)

        products = load_products()
        products.append({'sku': sku, 'name': name, 'category': category, 'region': region, 'inventory': float(inventory), 'price': float(price), 'reorder_level': float(reorder_level)})
        save_products(products)
        flash('Product added', 'success')
        return redirect(url_for('products'))

    return render_template('add_product.html')


@app.route('/products/edit/<sku>', methods=['GET', 'POST'])
@login_required
def edit_product(sku):
    products = load_products()
    prod = next((p for p in products if p.get('sku') == sku), None)
    if not prod:
        flash('Product not found', 'danger')
        return redirect(url_for('products'))

    if request.method == 'POST':
        prod['name'] = request.form.get('name')
        prod['category'] = request.form.get('category')
        prod['region'] = request.form.get('region')
        prod['inventory'] = float(request.form.get('inventory', 0))
        prod['price'] = float(request.form.get('price', 0))
        prod['reorder_level'] = float(request.form.get('reorder_level', 0))
        save_products(products)
        flash('Product updated', 'success')
        return redirect(url_for('products'))

    return render_template('edit_product.html', product=prod)


@app.route('/products/delete/<sku>', methods=['POST'])
@login_required
def delete_product(sku):
    products = load_products()
    products = [p for p in products if p.get('sku') != sku]
    save_products(products)
    flash('Product deleted', 'info')
    return redirect(url_for('products'))


@app.route('/export/products')
@login_required
def export_products():
    products = load_products()
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(['sku','name','category','region','inventory','price','reorder_level'])
    for p in products:
        writer.writerow([p.get('sku'), p.get('name'), p.get('category'), p.get('region'), p.get('inventory'), p.get('price'), p.get('reorder_level')])
    mem = io.BytesIO()
    mem.write(si.getvalue().encode('utf-8'))
    mem.seek(0)
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name='products.csv')


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
    # Placeholder AI insights generated from products
    products = load_products()
    insights = []
    if not products:
        insights.append('No product data available. Upload inventory to generate AI insights.')
    else:
        insights.append('Top product by demand: SKU-1001')
        insights.append('High demand category: Widgets')
        insights.append('Seasonal peak: Q4')

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
    defaults = {
        'profile_picture': session.get('user_settings', {}).get('profile_picture', ''),
        'username': current_user.id,
        'full_name': session.get('user_settings', {}).get('full_name', ''),
        'email': session.get('user_settings', {}).get('email', ''),
        'role': getattr(current_user, 'role', 'user'),
        'theme': session.get('user_settings', {}).get('theme', 'light'),
    }

    if request.method == 'POST':
        form_name = request.form.get('form_name')

        # PROFILE form
        if form_name == 'profile':
            pic = request.files.get('profile_picture')
            if pic and pic.filename:
                filename = secure_filename(pic.filename)
                target = os.path.join(UPLOAD_FOLDER, filename)
                pic.save(target)
                defaults['profile_picture'] = filename

            # basic validation
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()
            if not full_name or not email:
                flash('Full name and email are required.', 'danger')
                return redirect(url_for('settings'))
            defaults['full_name'] = full_name
            defaults['email'] = email
            # save
            session.setdefault('user_settings', {}).update({
                'profile_picture': defaults['profile_picture'],
                'full_name': defaults['full_name'],
                'email': defaults['email']
            })
            flash('Profile updated.', 'success')
            return redirect(url_for('settings'))

        # APPEARANCE form
        if form_name == 'appearance':
            theme = request.form.get('theme', 'light')
            session.setdefault('user_settings', {})['theme'] = theme
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
            users = load_users()
            user_record = users.get(current_user.id)
            if not user_record or not check_password_hash(user_record.get('password_hash',''), current_pw):
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for('settings'))
            if new_pw != confirm_pw:
                flash('New passwords do not match.', 'danger')
                return redirect(url_for('settings'))
            users[current_user.id]['password_hash'] = generate_password_hash(new_pw)
            save_users(users)
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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
