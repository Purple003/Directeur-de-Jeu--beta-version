from sqlalchemy import inspect

from app.database import DB_SCHEMA, engine


def main() -> None:
    insp = inspect(engine)
    tables = set(insp.get_table_names(schema=DB_SCHEMA))
    expected = {
        "courses",
        "questions",
        "player",
        "player_progress",
        "level_progress",
        "sessions",
        "answers",
        "emotions",
        "xapi_statements",
        "users",
    }
    missing = sorted(expected - tables)
    print(f"Schema: {DB_SCHEMA}")
    print(f"Tables found ({len(tables)}): {sorted(tables)}")
    if missing:
        print(f"Missing ({len(missing)}): {missing}")
        raise SystemExit(1)
    print("OK: all expected tables exist.")


if __name__ == "__main__":
    main()
