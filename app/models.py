from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

db = SQLAlchemy()

class Serie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    synopsis = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String, nullable=True)
    rating = db.Column(db.Float, nullable=True)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    serie_id = db.Column(db.Integer, db.ForeignKey("serie.id"), nullable=False)
    score = db.Column(db.Integer, nullable=False)  # entre 1 et 5
    __table_args__ = (db.UniqueConstraint('user_id', 'serie_id', name='unique_user_serie_rating'),)

class SeriesTerm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    serie_id = db.Column(db.Integer, db.ForeignKey("serie.id"), nullable=False, index=True)
    term = db.Column(db.String, nullable=False, index=True)
    count = db.Column(db.Float, nullable=False, default=0)
    __table_args__ = (
        db.UniqueConstraint('serie_id', 'term', name='unique_serie_term'),
    )
