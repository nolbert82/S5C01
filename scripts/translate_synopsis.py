import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path when invoked as a script
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.app import app  # ensures app.config and db are initialized
from app.models import db, Serie

try:
    # deep-translator uses Google Translate under the hood (no API key required)
    from deep_translator import GoogleTranslator
except ImportError as e:
    print("Missing dependency: deep-translator. Install with: pip install deep-translator", file=sys.stderr)
    raise


def translate_text(text: str, translator: GoogleTranslator, retries: int = 3, delay: float = 1.0) -> str:
    """Translate a single text string with basic retry/backoff.

    Args:
        text: English input text
        translator: Initialized GoogleTranslator(source='en', target='fr')
        retries: Number of retries on transient errors
        delay: Base delay between retries
    Returns:
        Translated French text
    """
    attempt = 0
    last_exc = None
    while attempt <= retries:
        try:
            return translator.translate(text)
        except Exception as exc:  # network or rate limiting
            last_exc = exc
            # Exponential backoff
            sleep_s = delay * (2 ** attempt)
            time.sleep(sleep_s)
            attempt += 1
    # If still failing, re-raise the last exception
    raise last_exc  # type: ignore[misc]


def backup_synopses(series, out_dir: str) -> str:
    """Save a JSON backup of current synopses before modification.

    Returns the path to the backup file.
    """
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"synopsis_backup_{ts}.json")
    payload = {s.id: {"name": s.name, "synopsis": s.synopsis} for s in series}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def main():
    parser = argparse.ArgumentParser(description="Translate all series synopses from English to French.")
    parser.add_argument("--batch", type=int, default=25, help="Commit every N updates (default: 25)")
    parser.add_argument("--sleep", type=float, default=0.5, help="Sleep seconds between calls to avoid rate limits")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist changes, just show what would change")
    parser.add_argument("--only-empty", action="store_true", help="Only translate when synopsis is empty/null")
    parser.add_argument("--limit", type=int, default=0, help="Translate at most N items (0 = no limit)")
    parser.add_argument("--backup-dir", default="instance", help="Directory to store JSON backup (default: instance)")
    args = parser.parse_args()

    with app.app_context():
        # Build the base query
        q = Serie.query
        if args.only_empty:
            q = q.filter((Serie.synopsis.is_(None)) | (Serie.synopsis == ""))
        else:
            q = q.filter(Serie.synopsis.isnot(None)).filter(Serie.synopsis != "")

        series = q.order_by(Serie.id.asc()).all()
        if args.limit and args.limit > 0:
            series = series[: args.limit]

        if not series:
            print("No series found matching criteria.")
            return 0

        total = len(series)
        print(f"Found {total} series to process.")

        # Backup current synopses (for safety)
        backup_path = backup_synopses(series, args.backup_dir)
        print(f"Backup saved to: {backup_path}")

        translator = GoogleTranslator(source="en", target="fr")

        updated = 0
        errors = 0
        batch_count = 0

        for idx, s in enumerate(series, start=1):
            original = s.synopsis or ""
            if not original.strip():
                # If empty and we're not in only-empty mode, skip translating
                if not args.only_empty:
                    continue
            try:
                translated = translate_text(original, translator)
                # Normalize whitespace a bit
                translated_clean = translated.strip()
                if translated_clean and not args.dry_run:
                    s.synopsis = translated_clean
                    updated += 1
                    batch_count += 1
                    if batch_count >= args.batch:
                        db.session.commit()
                        batch_count = 0
                elif args.dry_run:
                    updated += 1
                print(f"[{idx}/{total}] {s.name}: OK")
            except Exception as exc:
                errors += 1
                print(f"[{idx}/{total}] {s.name}: ERROR: {exc}", file=sys.stderr)
            finally:
                if args.sleep > 0:
                    time.sleep(args.sleep)

        if not args.dry_run and batch_count > 0:
            db.session.commit()

        print("--- Summary ---")
        print(f"Updated: {updated}")
        print(f"Errors:  {errors}")
        if args.dry_run:
            print("Dry-run mode: no changes saved.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
