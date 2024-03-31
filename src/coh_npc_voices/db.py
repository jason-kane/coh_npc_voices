import sqlite3
import logging
import sys
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("__name__")


db_connection = None

def get_cursor():
    return db_connection.cursor()

def commit():
    db_connection.commit()

def prepare_database():
    global db_connection

    if not os.path.exists("voices.db"):
        # first time with the database
        log.info("Initializing new database")
        db_connection = sqlite3.connect("voices.db")
        cursor = get_cursor()
        cursor.execute("CREATE TABLE settings(dbversion)")
        cursor.execute("INSERT INTO settings VALUES(:version)", {"version": "0.1"})
        commit()
    else:
        db_connection = sqlite3.connect("voices.db")
        cursor = get_cursor()

    dbversion = cursor.execute("select dbversion from settings").fetchone()[0]
    log.info(f"Database is version {dbversion}")
    if dbversion == "0.1":
        log.info("migrating to db schema 0.2")
        cursor.execute("UPDATE settings SET dbversion = '0.2'")
        # base character table, one row per npc/category
        cursor.execute("""
            CREATE TABLE character (
                id INTEGER PRIMARY KEY, 
                name VARCHAR(64) NOT NULL,
                engine VARCHAR(64) NOT NULL,
                category TEXT CHECK( category IN ('npc', 'player', 'system')) NOT NULL DEFAULT 'npc'
            )""")

        # base engine configuration settings, things like language and voice
        # these settings are in the context of a specific NPC.  Exactly which
        # settings make sense depend on the engine, hence the key/value generic.
        cursor.execute("""
            CREATE TABLE base_tts_config (
                id INTEGER PRIMARY KEY,
                character_id INTEGER NOT NULL,
                key VARCHAR(64),
                value VARCHAR(64)
            )
        """)
        cursor.execute("""
            CREATE TABLE google_voices (
                id INTEGER PRIMARY KEY,
                name VARCHAR(64) NOT NULL,
                language_code VARCHAR(64) NOT NULL,
                ssml_gender VARCHAR(64) NOT NULL
            )""")
        cursor.execute("""
            CREATE TABLE phrases (
                id INTEGER PRIMARY KEY,
                character_id INTEGER NOT NULL,
                text VARCHAR(256)
            )
        """)
        cursor.execute("""
            CREATE TABLE effects (
                id INTEGER PRIMARY KEY,
                character_id INTEGER NOT NULL,
                effect_name VARCHAR(256)
            )
        """)
        cursor.execute("""
            CREATE TABLE effect_setting (
                id INTEGER PRIMARY KEY,
                effect_id INTEGER NOT NULL,
                key VARCHAR(256) NOT NULL,
                value VARCHAR(256)
            )
        """)         
        commit()
