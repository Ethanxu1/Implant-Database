from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
)
from flask_login import (
    LoginManager,
    login_user,
    login_required,
    logout_user,
    current_user,
)
from flask_migrate import Migrate
from database import db, Implant, User, Procedure, ProcedureImplant
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///inventory.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

db.init_app(app)

migrate = Migrate(app, db, render_as_batch=True)

# with app.app_context():
#     db.create_all()

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Updated dental implant brands
COMMON_BRANDS = ["Hiossen", "Megagen", "Astra"]


def get_filter_params():
    """Helper function to get current filter parameters"""
    return {
        "search": request.args.get("search", ""),
        "size_filter": request.args.get("size_filter", ""),
        "brand_filter": request.args.get("brand_filter", ""),
    }


def is_ajax():
    """Returns True when the request comes from our fetch() calls."""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def other_pending_qty(implant_id, exclude_procedure_id):
    """Sum of quantities for implant_id across all pending procedures except the given one."""
    return (
        db.session.query(db.func.sum(ProcedureImplant.quantity))
        .join(Procedure)
        .filter(
            Procedure.user_id == current_user.id,
            Procedure.status == "pending",
            Procedure.id != exclude_procedure_id,
            ProcedureImplant.implant_id == implant_id,
        )
        .scalar()
        or 0
    )


def build_redirect_url(endpoint, **extra_params):
    """Build redirect URL with current filter parameters"""
    params = get_filter_params()
    params.update(extra_params)
    return redirect(url_for(endpoint, **params))


@app.route("/")
@login_required
def index():
    # Get search and filter parameters
    search = request.args.get("search", "")
    size_filter = request.args.get("size_filter", "")
    brand_filter = request.args.get("brand_filter", "")

    # Base query - only show current user's implants
    query = Implant.query.filter_by(user_id=current_user.id)

    # Apply search filter (for brand)
    if search:
        query = query.filter(Implant.brand.ilike(f"%{search}%"))

    # Apply size filter (partial matching)
    if size_filter:
        query = query.filter(Implant.size.ilike(f"%{size_filter}%"))

    # Apply brand filter
    if brand_filter:
        query = query.filter(Implant.brand == brand_filter)

    # Get all implants and sort by brand, then size
    implants = query.order_by(Implant.brand, Implant.size).all()

    # Get unique sizes for filter dropdown
    sizes = (
        db.session.query(Implant.size)
        .filter_by(user_id=current_user.id)
        .distinct()
        .all()
    )
    sizes = [size[0] for size in sizes]
    sizes.sort()

    # Get unique brands for filter dropdown
    brands = (
        db.session.query(Implant.brand)
        .filter_by(user_id=current_user.id)
        .distinct()
        .all()
    )
    brands = [brand[0] for brand in brands]
    brands.sort()

    # Identify low stock items
    low_stock_items = [implant for implant in implants if implant.is_low_stock()]

    # Compute pending quantities per implant (sum across all pending procedures)
    pending_rows = (
        db.session.query(
            ProcedureImplant.implant_id, db.func.sum(ProcedureImplant.quantity)
        )
        .join(Procedure)
        .filter(Procedure.user_id == current_user.id, Procedure.status == "pending")
        .group_by(ProcedureImplant.implant_id)
        .all()
    )
    pending_counts = {implant_id: total for implant_id, total in pending_rows}

    return render_template(
        "index.html",
        implants=implants,
        sizes=sizes,
        brands=brands,
        low_stock_items=low_stock_items,
        search=search,
        size_filter=size_filter,
        brand_filter=brand_filter,
        common_brands=COMMON_BRANDS,
        pending_counts=pending_counts,
    )


# Authentication routes
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get("next")
            return redirect(next_page) if next_page else redirect(url_for("index"))
        else:
            flash("Invalid username or password", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            flash("Passwords do not match", "danger")
            return render_template("register.html")

        if User.query.filter_by(username=username).first():
            flash("Username already exists", "danger")
            return render_template("register.html")

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html")


@app.route("/change_password", methods=["POST"])
@login_required
def change_password():
    current_password = request.form["current_password"]
    new_password = request.form["new_password"]
    confirm_password = request.form["confirm_password"]

    if not current_user.check_password(current_password):
        flash("Current password is incorrect", "danger")
        return redirect(url_for("profile"))

    if new_password != confirm_password:
        flash("New passwords do not match", "danger")
        return redirect(url_for("profile"))

    current_user.set_password(new_password)
    db.session.commit()
    flash("Password changed successfully!", "success")
    return redirect(url_for("profile"))


@app.route("/delete_account", methods=["POST"])
@login_required
def delete_account():
    # Get password confirmation
    password = request.form["password"]

    if not current_user.check_password(password):
        flash("Password is incorrect. Account deletion canceled.", "danger")
        return redirect(url_for("profile"))

    # Store username for flash message
    username = current_user.username

    # Delete user (this will also delete all their implants due to cascade)
    db.session.delete(current_user)
    db.session.commit()

    flash(f'Account "{username}" has been permanently deleted.', "info")
    return redirect(url_for("login"))


# Implant management routes
@app.route("/add", methods=["GET", "POST"])
@login_required
def add_implant():
    filter_params = get_filter_params()

    if request.method == "POST":
        size = request.form["size"]
        brand = request.form.get("custom_brand") or request.form["brand"]
        stock = int(request.form["stock"])
        min_stock_val = request.form.get("min_stock", "").strip()
        min_stock = int(min_stock_val) if min_stock_val else None

        # Check if implant already exists for this user
        existing_implant = Implant.query.filter_by(
            size=size, brand=brand, user_id=current_user.id
        ).first()

        if existing_implant:
            flash("An implant with this size and brand already exists!", "warning")
            return render_template(
                "add_implant.html", common_brands=COMMON_BRANDS, **filter_params
            )

        new_implant = Implant(
            size=size,
            brand=brand,
            stock=stock,
            min_stock=min_stock,
            user_id=current_user.id,  # Associate with current user
        )
        db.session.add(new_implant)
        db.session.commit()

        flash("Implant added successfully!", "success")
        return build_redirect_url("index")

    return render_template(
        "add_implant.html", common_brands=COMMON_BRANDS, **filter_params
    )


@app.route("/edit/<int:implant_id>", methods=["GET", "POST"])
@login_required
def edit_implant(implant_id):
    # Only allow editing implants that belong to the current user
    implant = Implant.query.filter_by(
        id=implant_id, user_id=current_user.id
    ).first_or_404()
    filter_params = get_filter_params()

    if request.method == "POST":
        # Update implant data
        implant.size = request.form["size"]
        implant.brand = request.form.get("custom_brand") or request.form["brand"]
        implant.stock = int(request.form["stock"])
        min_stock_val = request.form.get("min_stock", "").strip()
        implant.min_stock = int(min_stock_val) if min_stock_val else None

        # Check if another implant already has this size and brand combination for this user
        existing_implant = Implant.query.filter(
            Implant.size == implant.size,
            Implant.brand == implant.brand,
            Implant.user_id == current_user.id,
            Implant.id != implant.id,
        ).first()

        if existing_implant:
            flash("Another implant with this size and brand already exists!", "warning")
            return render_template(
                "edit_implant.html",
                implant=implant,
                common_brands=COMMON_BRANDS,
                **filter_params,
            )

        db.session.commit()
        flash("Implant updated successfully!", "success")
        return build_redirect_url("index")

    return render_template(
        "edit_implant.html",
        implant=implant,
        common_brands=COMMON_BRANDS,
        **filter_params,
    )


@app.route("/use/<int:implant_id>", methods=["POST"])
@login_required
def use_implant(implant_id):
    # Only allow using implants that belong to the current user
    implant = Implant.query.filter_by(
        id=implant_id, user_id=current_user.id
    ).first_or_404()

    if implant.stock > 0:
        implant.stock -= 1
        db.session.commit()
        if is_ajax():
            return jsonify(
                {
                    "ok": True,
                    "new_stock": implant.stock,
                    "message": f"Used one {implant.brand} {implant.size}. Remaining: {implant.stock}",
                }
            )
        flash(
            f"Used one {implant.brand} {implant.size} implant. Remaining: {implant.stock}",
            "info",
        )
    else:
        if is_ajax():
            return jsonify(
                {"ok": False, "message": "Cannot use implant — stock is already zero!"}
            )
        flash("Cannot use implant - stock is already zero!", "warning")

    return build_redirect_url("index")


@app.route("/add_stock/<int:implant_id>", methods=["GET", "POST"])
@login_required
def add_stock(implant_id):
    # Only allow adding stock to implants that belong to the current user
    implant = Implant.query.filter_by(
        id=implant_id, user_id=current_user.id
    ).first_or_404()
    filter_params = get_filter_params()

    if request.method == "POST":
        quantity = int(request.form["quantity"])
        implant.stock += quantity
        db.session.commit()

        flash(
            f"Added {quantity} {implant.brand} {implant.size} implants. New stock: {implant.stock}",
            "success",
        )
        return build_redirect_url("index")

    return render_template(
        "update_stock.html", implant=implant, action="Add", **filter_params
    )


@app.route("/remove/<int:implant_id>")
@login_required
def remove_implant(implant_id):
    # Only allow removing implants that belong to the current user
    implant = Implant.query.filter_by(
        id=implant_id, user_id=current_user.id
    ).first_or_404()

    pending_ref = (
        ProcedureImplant.query.join(Procedure)
        .filter(
            Procedure.user_id == current_user.id,
            Procedure.status == "pending",
            ProcedureImplant.implant_id == implant_id,
        )
        .first()
    )
    if pending_ref:
        flash(
            f"Cannot remove {implant.brand} {implant.size} — it is reserved in a pending procedure.",
            "warning",
        )
        return build_redirect_url("index")

    db.session.delete(implant)
    db.session.commit()

    flash("Implant removed successfully!", "success")
    return build_redirect_url("index")


@app.route("/procedures")
@login_required
def procedures():
    # Pop undo_id from session — only shows the undo banner on the first view
    undo_id = session.pop("undo_id", None)
    undo_procedure = None
    if undo_id:
        undo_procedure = Procedure.query.filter_by(
            id=undo_id, user_id=current_user.id, status="completed"
        ).first()

    # Clean up any stale completed procedures (undo window has passed)
    stale = Procedure.query.filter_by(user_id=current_user.id, status="completed").all()
    deleted_any = False
    for p in stale:
        if p != undo_procedure:
            db.session.delete(p)
            deleted_any = True
    if deleted_any:
        db.session.commit()

    pending = (
        Procedure.query.filter_by(user_id=current_user.id, status="pending")
        .order_by(Procedure.date.asc(), Procedure.patient_name.asc())
        .all()
    )

    all_pending_rows = (
        db.session.query(
            ProcedureImplant.implant_id, db.func.sum(ProcedureImplant.quantity)
        )
        .join(Procedure)
        .filter(Procedure.user_id == current_user.id, Procedure.status == "pending")
        .group_by(ProcedureImplant.implant_id)
        .all()
    )
    total_pending = {implant_id: total for implant_id, total in all_pending_rows}

    over_stock_set = set()
    for proc in pending:
        for item in proc.items:
            if (
                item.implant
                and total_pending.get(item.implant_id, 0) > item.implant.stock
            ):
                over_stock_set.add(proc.id)
                break

    return render_template(
        "procedures.html",
        procedures=pending,
        undo_procedure=undo_procedure,
        over_stock_set=over_stock_set,
        total_pending=total_pending,
    )


@app.route("/procedures/new", methods=["GET", "POST"])
@login_required
def new_procedure():
    if request.method == "POST":
        patient_name = request.form["patient_name"].strip()
        if not patient_name:
            flash("Patient name is required.", "warning")
            return render_template("procedure_new.html")

        date_str = request.form.get("date", "").strip()
        date_val = None
        if date_str:
            try:
                date_val = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date format.", "warning")
                return render_template("procedure_new.html")

        procedure = Procedure(
            patient_name=patient_name, date=date_val, user_id=current_user.id
        )
        db.session.add(procedure)
        db.session.commit()
        return redirect(url_for("edit_procedure", procedure_id=procedure.id))

    return render_template("procedure_new.html")


@app.route("/procedures/<int:procedure_id>/edit", methods=["GET", "POST"])
@login_required
def edit_procedure(procedure_id):
    procedure = Procedure.query.filter_by(
        id=procedure_id, user_id=current_user.id, status="pending"
    ).first_or_404()

    size_filter = request.args.get("size_filter", "")
    brand_filter = request.args.get("brand_filter", "")

    if request.method == "POST":
        patient_name = request.form["patient_name"].strip()
        if not patient_name:
            flash("Patient name is required.", "warning")
            return redirect(
                url_for(
                    "edit_procedure",
                    procedure_id=procedure_id,
                    size_filter=size_filter,
                    brand_filter=brand_filter,
                )
            )
        procedure.patient_name = patient_name
        date_str = request.form.get("date", "").strip()
        procedure.date = None
        if date_str:
            try:
                procedure.date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date format.", "warning")
        db.session.commit()
        flash("Procedure details saved.", "success")
        return redirect(
            url_for(
                "edit_procedure",
                procedure_id=procedure_id,
                size_filter=size_filter,
                brand_filter=brand_filter,
            )
        )

    # Implant picker query
    query = Implant.query.filter_by(user_id=current_user.id)
    if size_filter:
        query = query.filter(Implant.size.ilike(f"%{size_filter}%"))
    if brand_filter:
        query = query.filter(Implant.brand == brand_filter)
    picker_implants = query.order_by(Implant.brand, Implant.size).all()

    brands = [
        b[0]
        for b in db.session.query(Implant.brand)
        .filter_by(user_id=current_user.id)
        .distinct()
        .all()
    ]
    brands.sort()

    # Compute other_pending_counts: sum of qty in all OTHER pending procedures per implant
    other_pending_rows = (
        db.session.query(
            ProcedureImplant.implant_id, db.func.sum(ProcedureImplant.quantity)
        )
        .join(Procedure)
        .filter(
            Procedure.user_id == current_user.id,
            Procedure.status == "pending",
            Procedure.id != procedure_id,
        )
        .group_by(ProcedureImplant.implant_id)
        .all()
    )
    other_pending_counts = {
        implant_id: total for implant_id, total in other_pending_rows
    }

    return render_template(
        "procedure_edit.html",
        procedure=procedure,
        picker_implants=picker_implants,
        brands=brands,
        size_filter=size_filter,
        brand_filter=brand_filter,
        other_pending_counts=other_pending_counts,
    )


@app.route("/procedures/<int:procedure_id>/add-implant", methods=["POST"])
@login_required
def add_procedure_implant(procedure_id):
    procedure = Procedure.query.filter_by(
        id=procedure_id, user_id=current_user.id, status="pending"
    ).first_or_404()

    implant_id = int(request.form["implant_id"])
    quantity = max(1, int(request.form.get("quantity", 1)))
    implant = Implant.query.filter_by(
        id=implant_id, user_id=current_user.id
    ).first_or_404()

    existing = ProcedureImplant.query.filter_by(
        procedure_id=procedure_id, implant_id=implant_id
    ).first()

    is_existing = existing is not None
    if existing:
        existing.quantity += quantity
        item = existing
    else:
        item = ProcedureImplant(
            procedure_id=procedure_id, implant_id=implant_id, quantity=quantity
        )
        db.session.add(item)
    db.session.commit()

    other_pending = other_pending_qty(implant_id, procedure_id)
    available = max(0, implant.stock - other_pending)
    warning = item.quantity > available

    if is_ajax():
        return jsonify(
            {
                "ok": True,
                "item_id": item.id,
                "quantity": item.quantity,
                "brand": implant.brand,
                "size": implant.size,
                "is_existing": is_existing,
                "stock": implant.stock,
                "available": available,
                "warning": warning,
            }
        )

    size_filter = request.form.get("size_filter", "")
    brand_filter = request.form.get("brand_filter", "")
    return redirect(
        url_for(
            "edit_procedure",
            procedure_id=procedure_id,
            size_filter=size_filter,
            brand_filter=brand_filter,
        )
    )


@app.route(
    "/procedures/<int:procedure_id>/item/<int:item_id>/set-quantity", methods=["POST"]
)
@login_required
def set_procedure_item_quantity(procedure_id, item_id):
    Procedure.query.filter_by(
        id=procedure_id, user_id=current_user.id, status="pending"
    ).first_or_404()
    item = ProcedureImplant.query.filter_by(
        id=item_id, procedure_id=procedure_id
    ).first_or_404()

    quantity = int(request.form.get("quantity", 1))

    if quantity <= 0:
        db.session.delete(item)
        db.session.commit()
        return jsonify({"ok": True, "removed": True})

    item.quantity = quantity
    db.session.commit()

    implant = Implant.query.filter_by(
        id=item.implant_id, user_id=current_user.id
    ).first()
    warning = False
    if implant:
        available = max(
            0, implant.stock - other_pending_qty(item.implant_id, procedure_id)
        )
        warning = item.quantity > available

    return jsonify(
        {"ok": True, "removed": False, "quantity": item.quantity, "warning": warning}
    )


@app.route(
    "/procedures/<int:procedure_id>/remove-implant/<int:item_id>", methods=["POST"]
)
@login_required
def remove_procedure_implant(procedure_id, item_id):
    Procedure.query.filter_by(
        id=procedure_id, user_id=current_user.id, status="pending"
    ).first_or_404()
    item = ProcedureImplant.query.filter_by(
        id=item_id, procedure_id=procedure_id
    ).first_or_404()
    db.session.delete(item)
    db.session.commit()

    if is_ajax():
        return jsonify({"ok": True})

    size_filter = request.form.get("size_filter", "")
    brand_filter = request.form.get("brand_filter", "")
    return redirect(
        url_for(
            "edit_procedure",
            procedure_id=procedure_id,
            size_filter=size_filter,
            brand_filter=brand_filter,
        )
    )


@app.route("/procedures/<int:procedure_id>/confirm", methods=["POST"])
@login_required
def confirm_procedure(procedure_id):
    procedure = Procedure.query.filter_by(
        id=procedure_id, user_id=current_user.id, status="pending"
    ).first_or_404()

    if not procedure.items:
        if is_ajax():
            return jsonify(
                {"ok": False, "message": "Cannot confirm a procedure with no implants."}
            )
        flash("Cannot confirm a procedure with no implants.", "warning")
        return redirect(url_for("procedures"))

    # Check all items have sufficient stock before making any changes
    insufficient = []
    for item in procedure.items:
        implant = Implant.query.filter_by(
            id=item.implant_id, user_id=current_user.id
        ).first()
        available = (
            max(0, implant.stock - other_pending_qty(item.implant_id, procedure_id))
            if implant
            else 0
        )
        if not implant or item.quantity > available:
            name = f"{implant.brand} {implant.size}" if implant else "(deleted implant)"
            insufficient.append(f"{name} (need {item.quantity}, available {available})")
    if insufficient:
        msg = f"Insufficient stock: {', '.join(insufficient)}."
        if is_ajax():
            return jsonify({"ok": False, "message": msg})
        flash(msg, "warning")
        return redirect(url_for("procedures"))

    for item in procedure.items:
        implant = Implant.query.filter_by(
            id=item.implant_id, user_id=current_user.id
        ).first()
        if implant:
            implant.stock -= item.quantity

    procedure.status = "completed"
    db.session.commit()

    if is_ajax():
        return jsonify(
            {
                "ok": True,
                "procedure_id": procedure.id,
                "message": f"Procedure for {procedure.patient_name} confirmed — stock updated.",
            }
        )

    session["undo_id"] = procedure.id
    flash(
        f"Procedure for {procedure.patient_name} confirmed — stock updated.", "success"
    )
    return redirect(url_for("procedures"))


@app.route("/procedures/<int:procedure_id>/undo", methods=["POST"])
@login_required
def undo_procedure(procedure_id):
    procedure = Procedure.query.filter_by(
        id=procedure_id, user_id=current_user.id, status="completed"
    ).first_or_404()

    for item in procedure.items:
        implant = Implant.query.filter_by(
            id=item.implant_id, user_id=current_user.id
        ).first()
        if implant:
            implant.stock += item.quantity

    procedure.status = "pending"
    db.session.commit()

    if is_ajax():
        return jsonify({"ok": True})

    flash(
        f"Procedure for {procedure.patient_name} has been restored to pending.", "info"
    )
    return redirect(url_for("procedures"))


@app.route("/procedures/<int:procedure_id>/cancel", methods=["POST"])
@login_required
def cancel_procedure(procedure_id):
    procedure = Procedure.query.filter_by(
        id=procedure_id, user_id=current_user.id
    ).first_or_404()
    patient_name = procedure.patient_name
    db.session.delete(procedure)
    db.session.commit()

    if is_ajax():
        return jsonify(
            {"ok": True, "message": f"Procedure for {patient_name} has been cancelled."}
        )

    flash(f"Procedure for {patient_name} has been cancelled.", "info")
    return redirect(url_for("procedures"))


@app.route("/update_min_stock/<int:implant_id>", methods=["POST"])
@login_required
def update_min_stock(implant_id):
    # Only allow updating min stock for implants that belong to the current user
    implant = Implant.query.filter_by(
        id=implant_id, user_id=current_user.id
    ).first_or_404()
    new_min_stock = int(request.form["min_stock"])

    implant.min_stock = new_min_stock
    db.session.commit()

    flash("Minimum stock level updated!", "success")
    return build_redirect_url("index")


# def create_default_user():
#     """Create a default user if none exists"""
#     with app.app_context():
#         if not User.query.first():
#             user = User(username="user")
#             user.set_password("password123")
#             db.session.add(user)
#             db.session.commit()
#             print("Default user created: username='user', password='password123'")


def init_db():
    """Initialize the database"""
    with app.app_context():
        db.drop_all()
        db.create_all()
        # create_default_user()
        print("Database initialized!")


if __name__ == "__main__":
    # Uncomment the line below to reset the database (will delete all data)
    # init_db()
    app.run(debug=False)
