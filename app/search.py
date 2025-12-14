from __future__ import annotations

import os
import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from scipy.sparse import csr_matrix, vstack
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.preprocessing import normalize

# Modèles de base de données (pour le chargement via la BDD)
try:
    from app.models import db, Serie, SeriesTerm  # type: ignore
except Exception:
    # Permet l'importation de ce module dans des contextes où app/models n'est pas prêt
    db = None
    Serie = None
    SeriesTerm = None

class SearchEngine:

    def __init__(self, series_counts: Dict[str, Dict[str, float]]):
        # Garder l'ordre des séries stable
        self.series_names: List[str] = list(series_counts.keys())
        self._name_to_index: Dict[str, int] = {n: i for i, n in enumerate(self.series_names)}

        # Vectoriser les comptes avec un vocabulaire fixe en utilisant DictVectorizer
        self._dv = DictVectorizer()
        counts_list = [series_counts[name] for name in self.series_names]
        if len(counts_list) == 0:
            # Initialisation vide, pas de caractéristiques, pas de lignes
            self._dv.fit([{}])  # créer un vocabulaire vide en toute sécurité
            self._tfidf = TfidfTransformer(norm="l2", use_idf=True, smooth_idf=True)
            self._X = csr_matrix((0, 0))
            return

        X_counts = self._dv.fit_transform(counts_list)

        # Transformation TF-IDF
        self._tfidf = TfidfTransformer(norm="l2", use_idf=True, smooth_idf=True)
        self._X = self._tfidf.fit_transform(X_counts)  # forme : (n_series, n_features)

        # Lignes pré-normalisées (l2) issues de TfidfTransformer, mais garder une normalisation de sécurité
        self._X = normalize(self._X, norm="l2", copy=False)


    @staticmethod
    def load_series_counts_from_db() -> Dict[str, Dict[str, float]]:
        # Charge les comptes de mots par série depuis la base de données (tables : Serie, SeriesTerm).
        # Retourne un mapping : { nom_serie: { terme: compte } }.
        series_counts: Dict[str, Dict[str, float]] = {}
        # S'assurer que les modèles de BDD sont disponibles
        if db is None or Serie is None or SeriesTerm is None:
            return series_counts

        try:
            q = (
                db.session.query(Serie.name, SeriesTerm.term, SeriesTerm.count)
                .join(SeriesTerm, SeriesTerm.serie_id == Serie.id)
                .filter(SeriesTerm.count > 0)
            )
            for s_name, term, count in q:
                if not s_name:
                    continue
                term_norm = SearchEngine._normalize_text(term or "")
                if not term_norm:
                    continue
                try:
                    c = float(count)
                except (TypeError, ValueError):
                    continue
                if c <= 0:
                    continue
                d = series_counts.setdefault(str(s_name), {})
                d[term_norm] = d.get(term_norm, 0.0) + c
        except Exception:
            # Au cas où les tables n'existent pas encore ou si la BDD n'est pas prête
            return {}

        return series_counts

    # Aides à la vectorisation
    # Correspond aux mots Unicode (lettres uniquement), autorisant les apostrophes internes.
    # Exemples correspondants : "été", "l'été", "naïve", "coöperate"
    _token_re = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*")

    @staticmethod
    def _normalize_text(text: str) -> str:
        # Normaliser en NFC et en minuscules pour une correspondance cohérente.
        return unicodedata.normalize("NFC", text).lower()

    def _query_to_counts(self, query: str) -> Dict[str, float]:
        # Normaliser la requête pour gérer les accents composés/combinés uniformément
        query = unicodedata.normalize("NFC", query)
        tokens = [self._normalize_text(t) for t in self._token_re.findall(query)]
        counts: Dict[str, float] = {}
        for t in tokens:
            counts[t] = counts.get(t, 0.0) + 1.0
        return counts

    def vectorize_query(self, query: str) -> csr_matrix:
        # S'il n'y a pas de caractéristiques, retourner un vecteur vide
        if self._X.shape[1] == 0:
            return csr_matrix((1, 0))
        counts = self._query_to_counts(query)
        if not counts:
            return csr_matrix((1, self._X.shape[1]))
        v = self._dv.transform([counts])
        v_tfidf = self._tfidf.transform(v)
        return normalize(v_tfidf, norm="l2")

    def user_profile_from_ratings(
        self, rated_items: Sequence[Tuple[str, float]]
    ) -> Tuple[Optional[csr_matrix], Optional[csr_matrix]]:
        # Construire des profils séparés pour les séries aimées et détestées.
        # Retourne un tuple : (profil_positif, profil_negatif).

        def _aggregate(rows: List[csr_matrix], weights: List[float]) -> Optional[csr_matrix]:
            if not rows:
                return None
            stacked = vstack(rows)
            w = np.asarray(weights).reshape(-1, 1)
            prof = (stacked.multiply(w)).sum(axis=0)
            prof = csr_matrix(prof)
            prof = normalize(prof, norm="l2")
            return prof

        pos_rows: List[csr_matrix] = []
        pos_weights: List[float] = []
        neg_rows: List[csr_matrix] = []
        neg_weights: List[float] = []

        for name, score in rated_items:
            idx = self._name_to_index.get(name)
            if idx is None:
                continue
            try:
                iv = int(round(float(score)))
            except (TypeError, ValueError):
                continue
            if iv == 3:
                continue  # note neutre, aucun impact
            magnitude = {1: 2.0, 2: 1.0, 4: 1.0, 5: 2.0}.get(iv)
            if magnitude is None:
                continue
            if iv >= 4:
                pos_rows.append(self._X[idx])
                pos_weights.append(magnitude)
            elif iv <= 2:
                neg_rows.append(self._X[idx])
                neg_weights.append(magnitude)

        return _aggregate(pos_rows, pos_weights), _aggregate(neg_rows, neg_weights)

    # Recherche / Recommandation
    def search(
        self,
        query: Optional[str] = None,
        user_profile_positive: Optional[csr_matrix] = None,
        user_profile_negative: Optional[csr_matrix] = None,
        top_n: int = 10,
        exclude_names: Optional[Iterable[str]] = None,
        alpha: float = 1.0,
        beta: float = 1.0,
        gamma: float = 1.0,
    ) -> List[Tuple[str, float]]:

        # Si l'index est vide (pas de séries ou pas de vocabulaire), rien à retourner
        if self._X.shape[0] == 0 or self._X.shape[1] == 0:
            return []

        exclude_set = set(exclude_names or [])

        sims = np.zeros(self._X.shape[0], dtype=float)

        if query:
            qv = self.vectorize_query(query)
            if qv.shape[1] == self._X.shape[1]:
                sims += alpha * (qv @ self._X.T).toarray().ravel()

        if user_profile_positive is not None and user_profile_positive.shape[1] == self._X.shape[1]:
            sims += beta * (user_profile_positive @ self._X.T).toarray().ravel()

        if user_profile_negative is not None and user_profile_negative.shape[1] == self._X.shape[1]:
            sims -= gamma * (user_profile_negative @ self._X.T).toarray().ravel()

        if not np.any(sims):
            # Si tous les signaux sont manquants, rien à classer
            return []

        # Normaliser les scores entre [0, 1] pour éviter les pourcentages négatifs en aval
        min_val = sims.min()
        max_val = sims.max()
        if max_val != min_val:
            sims = (sims - min_val) / (max_val - min_val)
        else:
            sims = np.zeros_like(sims)

        scored = []
        for i, name in enumerate(self.series_names):
            val = float(sims[i])
            if name in exclude_set:
                continue
            if val <= 0.0:
                continue
            scored.append((name, val))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[: max(0, int(top_n))]