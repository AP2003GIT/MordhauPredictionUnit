from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.main import ingest_history  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch recent Needys matches into SQLite.")
    parser.add_argument("--limit", type=int, default=9999)
    args = parser.parse_args()

    result = ingest_history(limit=args.limit)
    print(result)


if __name__ == "__main__":
    main()

