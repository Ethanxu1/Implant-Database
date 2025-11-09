from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from database import db, Implant, User
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

db.init_app(app)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Updated dental implant brands
COMMON_BRANDS = [
    'Hiossen', 'Megagen', 'Astra'
]

def get_filter_params():
    """Helper function to get current filter parameters"""
    return {
        'search': request.args.get('search', ''),
        'size_filter': request.args.get('size_filter', ''),
        'brand_filter': request.args.get('brand_filter', '')
    }

def build_redirect_url(endpoint, **extra_params):
    """Build redirect URL with current filter parameters"""
    params = get_filter_params()
    params.update(extra_params)
    return redirect(url_for(endpoint, **params))

@app.route('/')
@login_required
def index():
    # Get search and filter parameters
    search = request.args.get('search', '')
    size_filter = request.args.get('size_filter', '')
    brand_filter = request.args.get('brand_filter', '')
    
    # Base query - only show current user's implants
    query = Implant.query.filter_by(user_id=current_user.id)
    
    # Apply search filter (for brand)
    if search:
        query = query.filter(Implant.brand.ilike(f'%{search}%'))
    
    # Apply size filter (partial matching)
    if size_filter:
        query = query.filter(Implant.size.ilike(f'%{size_filter}%'))
    
    # Apply brand filter
    if brand_filter:
        query = query.filter(Implant.brand == brand_filter)
    
    # Get all implants and sort by brand, then size
    implants = query.order_by(Implant.brand, Implant.size).all()
    
    # Get unique sizes for filter dropdown
    sizes = db.session.query(Implant.size).filter_by(user_id=current_user.id).distinct().all()
    sizes = [size[0] for size in sizes]
    sizes.sort()
    
    # Get unique brands for filter dropdown
    brands = db.session.query(Implant.brand).filter_by(user_id=current_user.id).distinct().all()
    brands = [brand[0] for brand in brands]
    brands.sort()
    
    # Identify low stock items
    low_stock_items = [implant for implant in implants if implant.is_low_stock()]
    
    return render_template('index.html', 
                         implants=implants, 
                         sizes=sizes,
                         brands=brands,
                         low_stock_items=low_stock_items,
                         search=search,
                         size_filter=size_filter,
                         brand_filter=brand_filter,
                         common_brands=COMMON_BRANDS)

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return render_template('register.html')
        
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']
    
    if not current_user.check_password(current_password):
        flash('Current password is incorrect', 'danger')
        return redirect(url_for('profile'))
    
    if new_password != confirm_password:
        flash('New passwords do not match', 'danger')
        return redirect(url_for('profile'))
    
    current_user.set_password(new_password)
    db.session.commit()
    flash('Password changed successfully!', 'success')
    return redirect(url_for('profile'))

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    # Get password confirmation
    password = request.form['password']
    
    if not current_user.check_password(password):
        flash('Password is incorrect. Account deletion canceled.', 'danger')
        return redirect(url_for('profile'))
    
    # Store username for flash message
    username = current_user.username
    
    # Delete user (this will also delete all their implants due to cascade)
    db.session.delete(current_user)
    db.session.commit()
    
    flash(f'Account "{username}" has been permanently deleted.', 'info')
    return redirect(url_for('login'))

# Implant management routes
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_implant():
    filter_params = get_filter_params()
    
    if request.method == 'POST':
        size = request.form['size']
        brand = request.form.get('custom_brand') or request.form['brand']
        stock = int(request.form['stock'])
        min_stock = int(request.form['min_stock'])
        
        # Check if implant already exists for this user
        existing_implant = Implant.query.filter_by(
            size=size, 
            brand=brand, 
            user_id=current_user.id
        ).first()
        
        if existing_implant:
            flash('An implant with this size and brand already exists!', 'warning')
            return render_template('add_implant.html', common_brands=COMMON_BRANDS, **filter_params)
        
        new_implant = Implant(
            size=size, 
            brand=brand, 
            stock=stock, 
            min_stock=min_stock,
            user_id=current_user.id  # Associate with current user
        )
        db.session.add(new_implant)
        db.session.commit()
        
        flash('Implant added successfully!', 'success')
        return build_redirect_url('index')
    
    return render_template('add_implant.html', common_brands=COMMON_BRANDS, **filter_params)

@app.route('/edit/<int:implant_id>', methods=['GET', 'POST'])
@login_required
def edit_implant(implant_id):
    # Only allow editing implants that belong to the current user
    implant = Implant.query.filter_by(id=implant_id, user_id=current_user.id).first_or_404()
    filter_params = get_filter_params()
    
    if request.method == 'POST':
        # Update implant data
        implant.size = request.form['size']
        implant.brand = request.form.get('custom_brand') or request.form['brand']
        implant.stock = int(request.form['stock'])
        implant.min_stock = int(request.form['min_stock'])
        
        # Check if another implant already has this size and brand combination for this user
        existing_implant = Implant.query.filter(
            Implant.size == implant.size,
            Implant.brand == implant.brand,
            Implant.user_id == current_user.id,
            Implant.id != implant.id
        ).first()
        
        if existing_implant:
            flash('Another implant with this size and brand already exists!', 'warning')
            return render_template('edit_implant.html', implant=implant, common_brands=COMMON_BRANDS, **filter_params)
        
        db.session.commit()
        flash('Implant updated successfully!', 'success')
        return build_redirect_url('index')
    
    return render_template('edit_implant.html', implant=implant, common_brands=COMMON_BRANDS, **filter_params)

@app.route('/use/<int:implant_id>')
@login_required
def use_implant(implant_id):
    # Only allow using implants that belong to the current user
    implant = Implant.query.filter_by(id=implant_id, user_id=current_user.id).first_or_404()
    
    if implant.stock > 0:
        implant.stock -= 1
        db.session.commit()
        flash(f'Used one {implant.brand} {implant.size} implant. Remaining: {implant.stock}', 'info')
    else:
        flash('Cannot use implant - stock is already zero!', 'warning')
    
    return build_redirect_url('index')

@app.route('/add_stock/<int:implant_id>', methods=['GET', 'POST'])
@login_required
def add_stock(implant_id):
    # Only allow adding stock to implants that belong to the current user
    implant = Implant.query.filter_by(id=implant_id, user_id=current_user.id).first_or_404()
    filter_params = get_filter_params()
    
    if request.method == 'POST':
        quantity = int(request.form['quantity'])
        implant.stock += quantity
        db.session.commit()
        
        flash(f'Added {quantity} {implant.brand} {implant.size} implants. New stock: {implant.stock}', 'success')
        return build_redirect_url('index')
    
    return render_template('update_stock.html', implant=implant, action='Add', **filter_params)

@app.route('/remove/<int:implant_id>')
@login_required
def remove_implant(implant_id):
    # Only allow removing implants that belong to the current user
    implant = Implant.query.filter_by(id=implant_id, user_id=current_user.id).first_or_404()
    db.session.delete(implant)
    db.session.commit()
    
    flash('Implant removed successfully!', 'success')
    return build_redirect_url('index')

@app.route('/update_min_stock/<int:implant_id>', methods=['POST'])
@login_required
def update_min_stock(implant_id):
    # Only allow updating min stock for implants that belong to the current user
    implant = Implant.query.filter_by(id=implant_id, user_id=current_user.id).first_or_404()
    new_min_stock = int(request.form['min_stock'])
    
    implant.min_stock = new_min_stock
    db.session.commit()
    
    flash('Minimum stock level updated!', 'success')
    return build_redirect_url('index')

def create_default_user():
    """Create a default user if none exists"""
    with app.app_context():
        if not User.query.first():
            user = User(username='user')
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()
            print("Default user created: username='user', password='password123'")

def init_db():
    """Initialize the database"""
    with app.app_context():
        db.drop_all()
        db.create_all()
        create_default_user()
        print("Database initialized!")

if __name__ == '__main__':
    # Uncomment the line below to reset the database (will delete all data)
    # init_db()
    
    with app.app_context():
        db.create_all()
        create_default_user()
    app.run(debug=False)
