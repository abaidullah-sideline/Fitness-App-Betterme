import sqlite3
from backend.config import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                gender TEXT,
                age_group TEXT,
                bmi_category TEXT,
                fitness_goal TEXT,
                activity_level TEXT,
                dietary_preference TEXT,
                medical_conditions TEXT,
                allergies_intolerances TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS plans (
                plan_id TEXT PRIMARY KEY,
                user_id TEXT,
                plan_json TEXT,
                edit_history_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS day_logs (
                log_id TEXT PRIMARY KEY,
                user_id TEXT,
                plan_id TEXT,
                day_of_week TEXT,
                is_complete INTEGER DEFAULT 0,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS chat_threads (
                thread_id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chat_checkpoints (
                thread_id TEXT PRIMARY KEY,
                checkpoint_blob TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS memory_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                thread_id TEXT,
                summary_text TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS gif_metadata (
                gif_id TEXT PRIMARY KEY,
                exercise_name TEXT,
                muscle_group TEXT,
                difficulty TEXT,
                file_path TEXT
            );

            CREATE TABLE IF NOT EXISTS youtube_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                url TEXT,
                tags TEXT
            );
        """)
    conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply schema migrations for columns added after initial creation."""
    migrations = [
        "ALTER TABLE plans ADD COLUMN original_plan_json TEXT",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists


def init_db() -> None:
    pass  # replaced below — kept so callers importing the symbol don't break


def _init_db_impl() -> None:
    conn = get_connection()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                gender TEXT,
                age_group TEXT,
                bmi_category TEXT,
                fitness_goal TEXT,
                activity_level TEXT,
                dietary_preference TEXT,
                medical_conditions TEXT,
                allergies_intolerances TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS plans (
                plan_id TEXT PRIMARY KEY,
                user_id TEXT,
                plan_json TEXT,
                edit_history_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS day_logs (
                log_id TEXT PRIMARY KEY,
                user_id TEXT,
                plan_id TEXT,
                day_of_week TEXT,
                is_complete INTEGER DEFAULT 0,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS chat_threads (
                thread_id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chat_checkpoints (
                thread_id TEXT PRIMARY KEY,
                checkpoint_blob TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS memory_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                thread_id TEXT,
                summary_text TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS gif_metadata (
                gif_id TEXT PRIMARY KEY,
                exercise_name TEXT,
                muscle_group TEXT,
                difficulty TEXT,
                file_path TEXT
            );

            CREATE TABLE IF NOT EXISTS youtube_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                url TEXT,
                tags TEXT
            );
        """)
        _migrate(conn)
    conn.close()


# Replace stub and run immediately
init_db = _init_db_impl
init_db()


if __name__ == "__main__":
    print("Database initialised successfully")
    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    conn.close()
    print("Tables created:")
    for (name,) in tables:
        print(f"  - {name}")
