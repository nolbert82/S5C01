import unittest
import sys
import os

# 1. On récupère le chemin du dossier actuel
current_dir = os.path.dirname(os.path.abspath(__file__))

# 2. On ajoute ce dossier au "path" de Python
sys.path.append(current_dir)

# 3. TRUC MAGIQUE : On force Python à croire que le dossier "app" est un package
# Cela permet aux imports 'from app.models' dans app.py de fonctionner
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Il faut s'assurer que le dossier parent est aussi dans le path pour trouver 'app'
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

# Maintenant on peut importer
try:
    # On essaie d'importer depuis le dossier 'app'
    from app.app import app, db
    from app.models import User, Rating, Serie
except ImportError:
    # Si le fichier test est DANS le dossier app, on tente autrement
    from app import app, db
    from models import User, Rating, Serie

class TestExistingDB(unittest.TestCase):

    def setUp(self):
        """Configuration avant chaque test."""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        
        self.client = app.test_client()
        
        # Données de l'utilisateur de test temporaire
        self.test_username = "test_user_temp"
        self.test_email = "temp@test.com"
        self.test_password = "password123"

        # Contexte d'application
        self.app_context = app.app_context()
        self.app_context.push()

        # Nettoyage de sécurité (au cas où un test précédent aurait planté)
        self.cleanup_test_user()

        # Création de l'utilisateur de test UNIQUEMENT
        self.user = User(username=self.test_username, email=self.test_email)
        self.user.set_password(self.test_password)
        db.session.add(self.user)
        db.session.commit()

    def tearDown(self):
        """Nettoyage après chaque test."""
        self.cleanup_test_user()
        self.app_context.pop()

    def cleanup_test_user(self):
        """Supprime l'utilisateur temporaire et ses notes."""
        u = User.query.filter_by(username=self.test_username).first()
        if u:
            # On supprime ses notes d'abord
            Rating.query.filter_by(user_id=u.id).delete()
            db.session.delete(u)
            db.session.commit()

    # --- SECTION 1: RECHERCHE (Sur vos données existantes) ---

    def test_1_search_lost(self):
        """Cherche 'crash avion île' et vérifie si Lost sort."""
        print(f"\n[Test] Recherche 'crash avion île'...")
        response = self.client.get('/api/search?q=crash avion île')
        data = response.get_json()
        
        if not data:
            self.fail("Aucun résultat trouvé.")
        
        first_result_name = data[0][0]  
        print(f"   -> Résultat trouvé : {first_result_name}")
        self.assertIn("Lost", first_result_name)

    def test_2_search_nonsense(self):
        """Cherche n'importe quoi."""
        print(f"\n[Test] Recherche 'ifdgyvqo' (doit être vide)...")
        response = self.client.get('/api/search?q=ifdgyvqo')
        data = response.get_json()
        self.assertEqual(len(data), 0)
        print("   -> OK (Vide)")

    def test_3_search_breaking_bad(self):
        """Cherche 'meth' et espère trouver Breaking Bad."""
        print(f"\n[Test] Recherche 'meth'...")
        response = self.client.get('/api/search?q=meth')
        data = response.get_json()
        names = [d[0] for d in data]
        print(f"   -> Résultats : {names[:3]}")
        self.assertIn("Breaking Bad", names)

    # --- SECTION 2: RECOMMANDATIONS & NOTES ---

    def test_4_recommendations_empty(self):
        """Teste les recommandations sans notes (doit être vide)."""
        print(f"\n[Test] Recommandations sans notes...")
        self.client.post('/login', data={'username': self.test_username, 'password': self.test_password})
        
        response = self.client.get(f'/api/search?user_id={self.user.id}')
        data = response.get_json()
        self.assertEqual(len(data), 0)
        print("   -> OK (Vide)")

    def test_5_rating_flow(self):
        """Teste : Noter -> Vérifier -> Supprimer la note."""
        print(f"\n[Test] Cycle de notation...")
        
        # Connexion
        self.client.post('/login', data={'username': self.test_username, 'password': self.test_password})

        # On récupère une série réelle de votre BD pour la noter (ex: Lost)
        target_serie = Serie.query.filter(Serie.name.ilike("%Lost%")).first()
        if not target_serie:
            self.skipTest("Série 'Lost' introuvable dans la BD, impossible de tester la notation dessus.")

        serie_name = target_serie.name
        print(f"   -> Notation de '{serie_name}' à 5/5")

        # 1. Noter
        self.client.post('/api/rate', json={'serie_name': serie_name, 'rating': 5})

        # 2. Vérifier via l'API my_ratings
        res = self.client.get('/api/my_ratings')
        my_ratings = res.get_json()
        self.assertEqual(my_ratings.get(serie_name), 5)
        print("   -> Note bien enregistrée.")

        # 3. Supprimer la note
        self.client.post('/api/unrate', json={'serie_name': serie_name})
        
        # 4. Vérifier suppression
        res = self.client.get('/api/my_ratings')
        self.assertNotIn(serie_name, res.get_json())
        print("   -> Note supprimée.")

    # --- SECTION 3: ADMIN ---

    def test_6_admin_rights(self):
        """Teste la promotion admin."""
        print(f"\n[Test] Promotion Admin...")
        
        # Création d'un admin temporaire pour effectuer l'action
        admin_temp = User(username="admin_temp", email="admin@temp.com", is_admin=True)
        admin_temp.set_password("pass")
        db.session.add(admin_temp)
        db.session.commit()

        # Login admin
        self.client.post('/login', data={'username': 'admin_temp', 'password': 'pass'})

        # Promotion de l'user de test
        self.client.post(f'/admin/promote/{self.user.id}')
        
        promoted_user = User.query.get(self.user.id)
        self.assertTrue(promoted_user.is_admin)
        print(f"   -> {self.test_username} est maintenant Admin.")

        # Rétrogradation
        self.client.post(f'/admin/demote/{self.user.id}')
        demoted_user = User.query.get(self.user.id)
        self.assertFalse(demoted_user.is_admin)
        print(f"   -> {self.test_username} n'est plus Admin.")

        # Nettoyage de l'admin temporaire
        db.session.delete(admin_temp)
        db.session.commit()

if __name__ == '__main__':
    unittest.main()