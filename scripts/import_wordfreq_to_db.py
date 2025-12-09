#!/usr/bin/env python3
import os
import sys
import argparse
import unicodedata
from typing import Dict, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
try:
    os.chdir(BASE_DIR)
except OSError:
    pass

from app.app import app
from app.models import db, Serie, SeriesTerm
from app.search import SearchEngine


def import_dir(dir_path: str, truncate: bool = False, min_len: int = 3, max_terms: int = 3000):
    if not os.path.isdir(dir_path):
        print(f"Directory not found: {dir_path}")
        return

    total_terms = 0
    total_series = 0

    with app.app_context():
        db.create_all()
        series_list = Serie.query.order_by(Serie.id.asc()).all()
        if not series_list:
            print("No series found in DB. Aborting without creating any new series.")
            return

        filenames = [fn for fn in sorted(os.listdir(dir_path)) if fn.lower().endswith('.txt')]
        if len(filenames) != len(series_list):
            print(f"Warning: file count ({len(filenames)}) != DB series count ({len(series_list)}). Proceeding with min count.")

        max_idx = min(len(filenames), len(series_list))
        for i in range(max_idx):
            filename = filenames[i]
            serie = series_list[i]
            serie_name = os.path.splitext(filename)[0]
            file_path = os.path.join(dir_path, filename)
            if (serie.name or '').strip() != serie_name.strip():
                print(f"Note: DB serie '{serie.name}' mapped to file '{serie_name}'.")

            terms: Dict[str, float] = {}
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if not line or ':' not in line:
                            continue
                        term, count_str = line.split(':', 1)
                        term = SearchEngine._normalize_text(term.strip())
                        if len(term) < min_len:
                            continue
                        try:
                            count = float(count_str.strip())
                        except ValueError:
                            continue
                        if count > 0:
                            terms[term] = terms.get(term, 0.0) + count
            except OSError:
                continue

            if terms:
                sorted_terms: Tuple[Tuple[str, float], ...] = tuple(sorted(terms.items(), key=lambda kv: kv[1], reverse=True))
                terms = dict(sorted_terms[:max_terms])

            if truncate:
                SeriesTerm.query.filter_by(serie_id=serie.id).delete()
                db.session.commit()

            for term, count in terms.items():
                existing = SeriesTerm.query.filter_by(serie_id=serie.id, term=term).first()
                if existing:
                    existing.count = float(count)
                else:
                    db.session.add(SeriesTerm(serie_id=serie.id, term=term, count=float(count)))
            db.session.commit()

            total_series += 1
            total_terms += len(terms)
            print(f"Imported {len(terms)} terms for {serie_name}")

    print(f"Done. Series: {total_series}, Terms: {total_terms}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Import word frequency files into the database')
    parser.add_argument('--dir', default=os.path.join(BASE_DIR, 'data_word_frequency'), help='Directory with <serie>.txt files')
    parser.add_argument('--truncate', action='store_true', help='Delete existing terms for a serie before importing')
    parser.add_argument('--min-len', type=int, default=3, help='Minimum term length to keep (default: 3)')
    parser.add_argument('--max-terms', type=int, default=3000, help='Maximum terms to keep per series (default: 3000)')
    args = parser.parse_args()
    import_dir(args.dir, truncate=args.truncate, min_len=args.min_len, max_terms=args.max_terms)
