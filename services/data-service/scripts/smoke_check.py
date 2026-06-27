from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402
from app.storage import connect, database_stats, init_db  # noqa: E402


def main() -> None:
    with connect() as connection:
        init_db(connection)
        stats = database_stats(connection)

    print({"service": app.title, "stats": stats})


if __name__ == "__main__":
    main()

