from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_cors import CORS
from app.models import db, Serie, User, Rating
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
# Exemple fictif : normalement tu charges depuis tes sous-titres nettoyés
series_texts = {
    "Lost": "plane crash island survival mystery",
    "Breaking Bad": "meth chemistry teacher cartel drugs",
    "Dark": "time travel mystery family secrets",
    "Stranger Things": "kids supernatural monsters government",
    "The Office": "workplace comedy office humor",
    "Friends": "friendship comedy relationships",
    "Game of Thrones": "fantasy dragons medieval politics",
    "The Walking Dead": "zombies survival apocalypse",
    "House": "medical doctor diagnosis mystery",
    "Sherlock": "detective mystery crime london"
}
search_engine = None

# Remplace le moteur de recherche par un moteur TF-IDF construit
# depuis les fichiers de fréquences s'ils sont présents.
DATA_FREQ_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_word_frequency")
_series_counts = SearchEngine.load_series_counts_from_dir(DATA_FREQ_DIR)
if _series_counts:
    search_engine = SearchEngine(_series_counts)
else:
    # Fallback: build simple counts from example strings
    fallback_counts = {}
    for name, text in series_texts.items():
        counts = {}
        for token in text.split():
            token = token.strip().lower()
            if not token:
                continue
            counts[token] = counts.get(token, 0) + 1
        if counts:
            fallback_counts[name] = counts
    search_engine = SearchEngine(fallback_counts)

def populate_series_in_db(series_names):
    """Ajoute les séries dans la base si elles n'existent pas encore."""
    for name in series_names:
        if not Serie.query.filter_by(name=name).first():
            db.session.add(Serie(name=name))
    db.session.commit()

# --- ROUTES API ---
@app.route("/api/search")
def api_search():
    """
    Endpoint unifié de recherche/recommandation.
    - q (str, optionnel): requête libre. Si absent et utilisateur connecté,
      renvoie des recommandations basées sur ses notes.
    - top_n (int, optionnel): nombre de résultats (défaut: 10)
    - exclude_seen (bool, optionnel): exclut les séries déjà notées. Par défaut,
      vrai quand q est vide, faux sinon.
    Retour: liste de paires [serie_name, score]
    """
    query = (request.args.get("q") or "").strip()
    try:
        top_n = int(request.args.get("top_n", 10))
    except (TypeError, ValueError):
        top_n = 10
    # Unified behavior (combine when both are provided):
    # - If q and user_id: combine query + user profile
    # - If only q: simple search
    # - If only user_id: recommendations
    user_id = request.args.get("user_id")
    user_profile = None
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
            if rated_items:
                user_profile = search_engine.user_profile_from_ratings(rated_items)
        except (TypeError, ValueError):
            user_profile = None

    # If either signal is present, score now and return; client controls inclusion of user_id.
    if query or user_profile is not None:
        # Weighting: allow override; default to reduce user influence when both are present
        try:
            alpha = float(request.args.get("alpha", 1.0))
        except (TypeError, ValueError):
            alpha = 1.0
        default_beta = 0.005 if (query and user_profile is not None) else 1.0
        try:
            beta = float(request.args.get("beta", default_beta))
        except (TypeError, ValueError):
            beta = default_beta

        results = search_engine.search(
            query=query or None,
            user_profile=user_profile,
            top_n=top_n,
            alpha=alpha,
            beta=beta,
        )

        include_meta = str(request.args.get("include_meta", "0")).lower() in {"1", "true", "yes"}
        if include_meta:
            names = [name for name, _ in results]
            series = Serie.query.filter(Serie.name.in_(names)).all()
            meta = {s.name: {"synopsis": s.synopsis or "Aucune description disponible.",
                              "image_url": s.image_url or ""} for s in series}
            enriched = []
            for name, score in results:
                m = meta.get(name, {"synopsis": "Aucune description disponible.", "image_url": ""})
                enriched.append({
                    "name": name,
                    "score": score,
                    "synopsis": m.get("synopsis") or "Aucune description disponible.",
                    "image_url": m.get("image_url") or "",
                })
            return jsonify(enriched)

        return jsonify(results)
    exclude_seen_param = request.args.get("exclude_seen")
    exclude_seen = None
    if exclude_seen_param is not None:
        exclude_seen = str(exclude_seen_param).lower() == "true"

    # Construire un profil utilisateur à partir des notes (si connecté)
    user_profile = None
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
            user_profile = search_engine.user_profile_from_ratings(rated_items)

    if exclude_seen is None:
        exclude_seen = (query == "")

    exclude_names = rated_names if exclude_seen else set()

    results = search_engine.search(
        query=query or None,
        user_profile=user_profile,
        top_n=top_n,
        exclude_names=exclude_names,
    )
    return jsonify(results)

@app.route("/api/recommend")
def api_recommend():
    user_id = request.args.get("user_id")
    # TODO: implémenter reco content-based
    return jsonify({"user_id": user_id, "recommendations": ["Lost", "Dark", "Stranger Things"]})

@app.route("/api/rate", methods=["POST"])
@login_required
def rate_serie():
    data = request.get_json()
    serie_name = data.get("serie_name")
    rating = data.get("rating")
    
    if not serie_name or not rating:
        return jsonify({"success": False, "message": "Données manquantes"})
    
    # Chercher ou créer la série
    serie = Serie.query.filter_by(name=serie_name).first()
    if not serie:
        serie = Serie(name=serie_name)
        db.session.add(serie)
        db.session.commit()
    
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
    """Return metadata for a list of series names.
    Query params: names=comma,separated,names
    Response: { name: { synopsis, image_url } }
    """
    names_param = request.args.get("names", "").strip()
    if not names_param:
        return jsonify({})
    names = [n.strip() for n in names_param.split(",") if n.strip()]
    if not names:
        return jsonify({})
    series = Serie.query.filter(Serie.name.in_(names)).all()
    meta = {s.name: {
        "synopsis": s.synopsis or "Aucune description disponible.",
        "image_url": s.image_url or ""
    } for s in series}
    # include placeholders for missing
    for n in names:
        if n not in meta:
            meta[n] = {"synopsis": "Aucune description disponible.", "image_url": ""}
    return jsonify(meta)

# --- INTERFACE WEB ---
@app.route("/")
def index():
    # Rediriger vers la page de recherche comme page principale
    return redirect(url_for("search_page"))

@app.route("/search")
def search_page():
    query = request.args.get("q", "")
    return render_template("search.html", query=query)

@app.route("/recommendations")
@login_required
def recommendations_page():
    # Récupérer les recommandations pour l'utilisateur actuel
    recommendations = ["Lost", "Dark", "Stranger Things", "The Office", "House"]
    return render_template("recommendations.html", recommendations=[])

# --- AUTHENTIFICATION ---
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

# --- ADMIN ROUTES ---
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

# --- INITIALISATION ---
def create_admin_user():
    """Créer un utilisateur admin par défaut"""
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        admin = User(username="admin", email="admin@example.com", is_admin=True)
        admin.set_password("admin123")
        db.session.add(admin)
        
        # Créer aussi un utilisateur normal pour les tests
        user = User(username="user", email="user@example.com", is_admin=False)
        user.set_password("user123")
        db.session.add(user)
        
        db.session.commit()
        print("Utilisateurs par défaut créés : admin/admin123 et user/user123")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        # Populate DB with series from data_word_frequency if available
        try:
            populate_series_in_db(getattr(search_engine, 'series_names', []))
        except Exception:
            # Non-fatal in dev
            pass
        create_admin_user()
    app.run(debug=True)