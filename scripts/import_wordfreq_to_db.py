#!/usr/bin/env python3
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from app.app import app
from app.models import db, Serie, SeriesTerm
from app.search import SearchEngine


def import_dir(dir_path: str):
    if not os.path.isdir(dir_path):
        print(f"Directory not found: {dir_path}")
        return

    total_terms = 0
    total_series = 0

    with app.app_context():
        db.create_all()
        for filename in sorted(os.listdir(dir_path)):
            if not filename.lower().endswith('.txt'):
                continue
            serie_name = os.path.splitext(filename)[0]
            file_path = os.path.join(dir_path, filename)

            serie = Serie.query.filter_by(name=serie_name).first()
            if not serie:
                serie = Serie(name=serie_name)
                db.session.add(serie)
                db.session.commit()

            terms = {}
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if not line or ':' not in line:
                            continue
                        term, count_str = line.split(':', 1)
                        term = SearchEngine._normalize_text(term.strip())
                        try:
                            count = float(count_str.strip())
                        except ValueError:
                            continue
                        if count > 0:
                            terms[term] = terms.get(term, 0.0) + count
            except OSError:
                continue

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
    data_dir = os.path.join(BASE_DIR, 'data_word_frequency')
    import_dir(data_dir)

