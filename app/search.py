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

# DB models (for DB-backed loading)
try:
    from app.models import db, Serie, SeriesTerm  # type: ignore
except Exception:
    # Allow importing this module in contexts without app/models readiness
    db = None
    Serie = None
    SeriesTerm = None

class SearchEngine:
    """
    TF-IDF based search/recommendation engine.

    - Fits TF-IDF on per-series word-frequency dictionaries.
    - Supports query search (free text) and user-profile recommendations
      (weighted combination of rated series vectors).
    - Can combine both signals when both are provided.
    """

    def __init__(self, series_counts: Dict[str, Dict[str, float]]):
        # Keep series order stable
        self.series_names: List[str] = list(series_counts.keys())
        self._name_to_index: Dict[str, int] = {n: i for i, n in enumerate(self.series_names)}

        # Vectorize counts with a fixed vocabulary using DictVectorizer
        self._dv = DictVectorizer()
        counts_list = [series_counts[name] for name in self.series_names]
        if len(counts_list) == 0:
            # Initialize empty, no features, no rows
            self._dv.fit([{}])  # create empty vocabulary safely
            self._tfidf = TfidfTransformer(norm="l2", use_idf=True, smooth_idf=True)
            self._X = csr_matrix((0, 0))
            return

        X_counts = self._dv.fit_transform(counts_list)

        # TF-IDF transform
        self._tfidf = TfidfTransformer(norm="l2", use_idf=True, smooth_idf=True)
        self._X = self._tfidf.fit_transform(X_counts)  # shape: (n_series, n_features)

        # Pre-normalized rows (l2) from TfidfTransformer, but keep a safety normalize
        self._X = normalize(self._X, norm="l2", copy=False)

    # ----------------------
    # Building helpers
    # ----------------------
    @staticmethod
    def load_series_counts_from_dir(dir_path: str) -> Dict[str, Dict[str, float]]:
        """
        Load per-series word counts from `data_word_frequency`-style directory.
        Expects files named `<series>.txt` with lines `word:count`.
        Series names come from file stems.
        """
        series_counts: Dict[str, Dict[str, float]] = {}
        if not os.path.isdir(dir_path):
            return series_counts

        for filename in sorted(os.listdir(dir_path)):
            if not filename.lower().endswith(".txt"):
                continue
            series_name = os.path.splitext(filename)[0]
            file_path = os.path.join(dir_path, filename)
            counts: Dict[str, float] = {}
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or ":" not in line:
                            continue
                        term, count_str = line.split(":", 1)
                        term = SearchEngine._normalize_text(term.strip())
                        try:
                            count = float(count_str.strip())
                        except ValueError:
                            continue
                        if count > 0:
                            counts[term] = counts.get(term, 0.0) + count
                if counts:
                    series_counts[series_name] = counts
            except OSError:
                # Skip unreadable files
                continue

        return series_counts

    @staticmethod
    def load_series_counts_from_db() -> Dict[str, Dict[str, float]]:
        """
        Load per-series word counts from the database (tables: Serie, SeriesTerm).
        Returns a mapping: { series_name: { term: count } }.
        """
        series_counts: Dict[str, Dict[str, float]] = {}
        # Ensure DB models are available
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
            # In case tables do not exist yet or DB not ready
            return {}

        return series_counts

    # ----------------------
    # Vectorization helpers
    # ----------------------
    # Match Unicode words (letters only), allowing internal apostrophes.
    # Examples matched: "été", "l'été", "naïve", "coöperate"
    _token_re = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*")

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize to NFC and lowercase for consistent matching."""
        return unicodedata.normalize("NFC", text).lower()

    def _query_to_counts(self, query: str) -> Dict[str, float]:
        # Normalize query to handle composed/combined accents uniformly
        query = unicodedata.normalize("NFC", query)
        tokens = [self._normalize_text(t) for t in self._token_re.findall(query)]
        counts: Dict[str, float] = {}
        for t in tokens:
            counts[t] = counts.get(t, 0.0) + 1.0
        return counts

    def vectorize_query(self, query: str) -> csr_matrix:
        # If no features, return empty vector
        if self._X.shape[1] == 0:
            return csr_matrix((1, 0))
        counts = self._query_to_counts(query)
        if not counts:
            return csr_matrix((1, self._X.shape[1]))
        v = self._dv.transform([counts])
        v_tfidf = self._tfidf.transform(v)
        return normalize(v_tfidf, norm="l2")

    def user_profile_from_ratings(self, rated_items: Sequence[Tuple[str, float]]) -> csr_matrix:
        """
        Build a user profile vector as the weighted (by rating) combination
        of the user's rated series TF-IDF vectors.
        rated_items: sequence of (series_name, rating_score)
        """
        rows: List[csr_matrix] = []
        weights: List[float] = []
        def _map_rating(score_val: float) -> float:
            try:
                iv = int(round(float(score_val)))
            except (TypeError, ValueError):
                return 0.0
            # 1/5 terrible, 2/5 bad, 3/5 neutral, 4/5 good, 5/5 very good
            mapping = {1: -2.0, 2: -1.0, 3: 0.0, 4: 1.0, 5: 2.0}
            return mapping.get(iv, 0.0)

        for name, score in rated_items:
            idx = self._name_to_index.get(name)
            if idx is None:
                continue
            w = _map_rating(score)
            if w == 0.0:
                continue
            rows.append(self._X[idx])
            weights.append(w)

        if not rows:
            return csr_matrix((1, self._X.shape[1]))

        # Weighted sum of normalized vectors
        stacked = vstack(rows)
        w = np.asarray(weights).reshape(-1, 1)
        prof = (stacked.multiply(w)).sum(axis=0)
        prof = csr_matrix(prof)
        return normalize(prof, norm="l2")

    # ----------------------
    # Search / Recommend
    # ----------------------
    def search(
        self,
        query: Optional[str] = None,
        user_profile: Optional[csr_matrix] = None,
        top_n: int = 10,
        exclude_names: Optional[Iterable[str]] = None,
        alpha: float = 1.0,
        beta: float = 1.0,
    ) -> List[Tuple[str, float]]:
        """
        Compute relevance scores for all series and return top results.
        - If only `query` is provided: query-based search.
        - If only `user_profile` is provided: recommendation based on ratings.
        - If both are provided: combine vectors with weights alpha and beta.
        - Can exclude a set of series names from results (e.g., already rated).
        Returns: list of (series_name, score) sorted by score desc.
        """
        # If the index is empty (no series or no vocabulary), nothing to return
        if self._X.shape[0] == 0 or self._X.shape[1] == 0:
            return []

        exclude_set = set(exclude_names or [])

        parts: List[csr_matrix] = []
        weights: List[float] = []
        if query:
            qv = self.vectorize_query(query)
            parts.append(qv)
            weights.append(alpha)
        if user_profile is not None and user_profile.shape[1] == self._X.shape[1]:
            parts.append(user_profile)
            weights.append(beta)

        if not parts:
            # Nothing to score against
            return []

        # Weighted sum and normalize
        combined = None
        for p, w in zip(parts, weights):
            combined = p.multiply(w) if combined is None else combined + p.multiply(w)
        # Handle potential empty vector (e.g., query has no known tokens)
        if combined.shape[1] == 0:
            return []
        combined = normalize(combined, norm="l2")

        sims = (combined @ self._X.T).toarray().ravel()  # cosine similarities

        scored = []
        for i, name in enumerate(self.series_names):
            val = float(sims[i])
            if val <= 0.0:
                continue
            scored.append((name, val))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[: max(0, int(top_n))]
