from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_cors import CORS
from app.models import db, Serie, User, Rating, SeriesTerm
from app.search import SearchEngine
import os

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///series.db"
app.config["SECRET_KEY"] = "CLESECRETE"

# Configuration CORS pour permettre l'accès à l'API depuis l'extérieur
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Initialisation de Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
login_manager.login_message_category = 'info'

db.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Initialisation du moteur de recherche ---
with app.app_context():
    _series_counts = SearchEngine.load_series_counts_from_db()
    search_engine = SearchEngine(_series_counts)


# --- ROUTES API ---
@app.route("/api/search")
def api_search():
    query = (request.args.get("q") or "").strip()
    try:
        top_n = int(request.args.get("top_n", 15))
    except (TypeError, ValueError):
        top_n = 15
    # Cap to 15 max, non-negative
    top_n = max(0, min(top_n, 15))
    # Unified behavior (combine when both are provided):
    # - If q and user_id: combine query + user profile
    # - If only q: simple search
    # - If only user_id: recommendations
    user_id = request.args.get("user_id")
    user_profile_pos = None
    user_profile_neg = None
    rated_names_for_user_id = set()
    if user_id is not None:
        try:
            uid = int(user_id)
            user_ratings = Rating.query.filter_by(user_id=uid).all()
            rated_items = []
            for r in user_ratings:
                serie = Serie.query.get(r.serie_id)
                if not serie:
                    continue
                rated_items.append((serie.name, r.score))
                rated_names_for_user_id.add(serie.name)
            if rated_items:
                user_profile_pos, user_profile_neg = search_engine.user_profile_from_ratings(rated_items)
        except (TypeError, ValueError):
            user_profile_pos = None
            user_profile_neg = None

    has_profile_signal = any(p is not None for p in (user_profile_pos, user_profile_neg))
    # If either signal is present, score now and return; client controls inclusion of user_id.
    if query or has_profile_signal:
        # Weighting: allow override; default to reduce user influence when both are present
        try:
            alpha = float(request.args.get("alpha", 1.0))
        except (TypeError, ValueError):
            alpha = 1.0
        default_beta = 0.005 if (query and has_profile_signal) else 1.0
        try:
            beta = float(request.args.get("beta", default_beta))
        except (TypeError, ValueError):
            beta = default_beta
        try:
            gamma = float(request.args.get("gamma", beta))
        except (TypeError, ValueError):
            gamma = beta

        exclude_rated = (not query) and bool(rated_names_for_user_id)
        results = search_engine.search(
            query=query or None,
            user_profile_positive=user_profile_pos,
            user_profile_negative=user_profile_neg,
            top_n=top_n,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            exclude_names=rated_names_for_user_id if exclude_rated else None,
        )

        include_meta = str(request.args.get("include_meta", "0")).lower() in {"1", "true", "yes"}
        if include_meta:
            names = [name for name, _ in results]
            series = Serie.query.filter(Serie.name.in_(names)).all()
            default_poster = url_for('static', filename='image/default_poster.jpg')
            meta = {s.name: {"synopsis": s.synopsis or "Aucune description disponible.",
                              "image_url": (s.image_url or default_poster)} for s in series}
            enriched = []
            for name, score in results:
                m = meta.get(name, {"synopsis": "Aucune description disponible.", "image_url": default_poster})
                enriched.append({
                    "name": name,
                    "score": score,
                    "synopsis": m.get("synopsis") or "Aucune description disponible.",
                    "image_url": m.get("image_url") or default_poster,
                })
            return jsonify(enriched)

        return jsonify(results)
    exclude_seen_param = request.args.get("exclude_seen")
    exclude_seen = None
    if exclude_seen_param is not None:
        exclude_seen = str(exclude_seen_param).lower() == "true"

    # Construire un profil utilisateur à partir des notes (si connecté)
    user_profile_pos = None
    user_profile_neg = None
    rated_names = set()
    if current_user.is_authenticated:
        user_ratings = Rating.query.filter_by(user_id=current_user.id).all()
        rated_items = []
        for r in user_ratings:
            serie = Serie.query.get(r.serie_id)
            if not serie:
                continue
            rated_items.append((serie.name, r.score))
            rated_names.add(serie.name)
        if rated_items:
            user_profile_pos, user_profile_neg = search_engine.user_profile_from_ratings(rated_items)

    if exclude_seen is None:
        exclude_seen = (query == "")

    exclude_names = rated_names if exclude_seen else set()

    results = search_engine.search(
        query=query or None,
        user_profile_positive=user_profile_pos,
        user_profile_negative=user_profile_neg,
        top_n=top_n,
        exclude_names=exclude_names,
    )
    return jsonify(results)

@app.route("/api/rate", methods=["POST"])
@login_required
def rate_serie():
    data = request.get_json()
    serie_name = data.get("serie_name")
    rating = data.get("rating")
    
    if not serie_name or not rating:
        return jsonify({"success": False, "message": "Données manquantes"})
    
    # Chercher la série
    serie = Serie.query.filter_by(name=serie_name).first()
    
    # Vérifier si l'utilisateur a déjà noté cette série
    existing_rating = Rating.query.filter_by(
        user_id=current_user.id, 
        serie_id=serie.id
    ).first()
    
    if existing_rating:
        existing_rating.score = rating
    else:
        new_rating = Rating(
            user_id=current_user.id,
            serie_id=serie.id,
            score=rating
        )
        db.session.add(new_rating)
    
    db.session.commit()
    return jsonify({"success": True, "message": "Note enregistrée"})

@app.route("/api/unrate", methods=["POST"])
@login_required
def unrate_serie():
    data = request.get_json() or {}
    serie_name = data.get("serie_name")
    if not serie_name:
        return jsonify({"success": False, "message": "missing fields"}), 400
    serie = Serie.query.filter_by(name=serie_name).first()
    if not serie:
        return jsonify({"success": True})
    existing_rating = Rating.query.filter_by(user_id=current_user.id, serie_id=serie.id).first()
    if existing_rating:
        db.session.delete(existing_rating)
        db.session.commit()
    return jsonify({"success": True})

@app.route("/api/my_ratings")
@login_required
def api_my_ratings():
    ratings = Rating.query.filter_by(user_id=current_user.id).all()
    out = {}
    for r in ratings:
        serie = Serie.query.get(r.serie_id)
        if serie:
            out[serie.name] = int(r.score)
    return jsonify(out)

@app.route("/api/series_meta")
def api_series_meta():
    names_param = request.args.get("names", "").strip()
    if not names_param:
        return jsonify({})
    names = [n.strip() for n in names_param.split(",") if n.strip()]
    if not names:
        return jsonify({})
    series = Serie.query.filter(Serie.name.in_(names)).all()
    default_poster = url_for('static', filename='image/default_poster.jpg')
    meta = {s.name: {
        "synopsis": s.synopsis or "Aucune description disponible.",
        "image_url": (s.image_url or default_poster)
    } for s in series}
    # include placeholders for missing
    for n in names:
        if n not in meta:
            meta[n] = {"synopsis": "Aucune description disponible.", "image_url": default_poster}
    return jsonify(meta)

# --- INTERFACE WEB ---
@app.route("/")
def index():
    # La page de recherche est la page d'accueil
    return redirect(url_for("search_page"))

@app.route("/search")
def search_page():
    query = request.args.get("q", "")
    return render_template("search.html", query=query)

@app.route("/recommendations")
@login_required
def recommendations_page():
    return render_template("recommendations.html", recommendations=[])

@app.route("/my-ratings")
@login_required
def my_ratings_page():
    user_ratings = Rating.query.filter_by(user_id=current_user.id).all()
    items = []
    for r in user_ratings:
        serie = Serie.query.get(r.serie_id)
        if not serie:
            continue
        try:
            score = int(r.score)
        except Exception:
            score = 0
        items.append({"name": serie.name, "rating": score})
    items.sort(key=lambda x: x["name"].lower())
    return render_template("my_ratings.html", rated_items=items)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        remember_me = request.form.get("remember_me")
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember_me)
            flash(f"Bienvenue, {user.username} !", "success")
            next_page = request.args.get("next")
            return redirect(next_page) if next_page else redirect(url_for("search_page"))
        else:
            flash("Nom d'utilisateur ou mot de passe incorrect.", "error")
    
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        # Validation
        if password != confirm_password:
            flash("Les mots de passe ne correspondent pas.", "error")
            return render_template("register.html")
        
        if User.query.filter_by(username=username).first():
            flash("Ce nom d'utilisateur est déjà pris.", "error")
            return render_template("register.html")
        
        if User.query.filter_by(email=email).first():
            flash("Cette adresse email est déjà utilisée.", "error")
            return render_template("register.html")
        
        # Créer l'utilisateur
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash("Compte créé avec succès ! Vous pouvez maintenant vous connecter.", "success")
        return redirect(url_for("login"))
    
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for("search_page"))

@app.route("/admin/users")
@login_required
def admin_users():
    if not current_user.is_admin:
        flash("Accès refusé. Droits administrateur requis.", "error")
        return redirect(url_for("search_page"))
    
    users = User.query.all()
    return render_template("admin_users.html", users=users)

@app.route("/admin/promote/<int:user_id>", methods=["POST"])
@login_required
def admin_promote_user(user_id):
    if not current_user.is_admin:
        flash("Accès refusé.", "error")
        return redirect(url_for("search_page"))
    
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Vous ne pouvez pas modifier vos propres droits.", "error")
        return redirect(url_for("admin_users"))
    
    user.is_admin = True
    db.session.commit()
    flash(f"{user.username} a été promu administrateur.", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/demote/<int:user_id>", methods=["POST"])
@login_required
def admin_demote_user(user_id):
    if not current_user.is_admin:
        flash("Accès refusé.", "error")
        return redirect(url_for("search_page"))
    
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Vous ne pouvez pas modifier vos propres droits.", "error")
        return redirect(url_for("admin_users"))
    
    user.is_admin = False
    db.session.commit()
    flash(f"{user.username} n'est plus administrateur.", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/delete/<int:user_id>", methods=["POST"])
@login_required
def admin_delete_user(user_id):
    if not current_user.is_admin:
        flash("Accès refusé.", "error")
        return redirect(url_for("search_page"))
    
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Vous ne pouvez pas supprimer votre propre compte.", "error")
        return redirect(url_for("admin_users"))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f"L'utilisateur {username} a été supprimé.", "success")
    return redirect(url_for("admin_users"))


if __name__ == "__main__":
    app.run(debug=True)
