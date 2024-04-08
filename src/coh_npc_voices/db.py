import sqlite3
import logging
import sys
import os
import re
import hashlib
import enum
from datetime import datetime

from typing import List
from typing import Optional
from sqlalchemy import ForeignKey, select
from sqlalchemy import String, Enum, Integer
from sqlalchemy import orm, create_engine
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy_utils import database_exists, create_database


engine = create_engine("sqlite:///voices.db", echo=True)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("__name__")

def build_migrate():
    # it really doesn't exist.
    if not database_exists(engine.url):    
        create_database(engine.url)
        Base.metadata.create_all(engine)
    return

if not database_exists(engine.url):
    build_migrate()





# db_connection = None

# def get_cursor(fresh=False):
#     if not fresh and db_connection:
#         return db_connection.cursor()
#     else:
#         prepare_database()
#         return db_connection.cursor()

# def commit():
#     db_connection.commit()

# def prepare_database():
#     global db_connection

#     if not os.path.exists("voices.db"):
#         # first time with the database
#         log.info("Initializing new database")
#         db_connection = sqlite3.connect("voices.db")
#         cursor = get_cursor()
#         cursor.execute("""
#             CREATE TABLE settings (
#                 dbversion varchar(16) NOT NULL,
#                 logdir varchar(256) default NULL,
#             )""")
#         cursor.execute("INSERT INTO settings VALUES(:version)", {"version": "0.1"})
#         commit()
#     else:
#         db_connection = sqlite3.connect("voices.db")
#         cursor = get_cursor()

#     dbversion = cursor.execute("select dbversion from settings").fetchone()[0]
#     log.info(f"Database is version {dbversion}")
#     if dbversion == "0.1":
#         log.info("migrating to db schema 0.2")
#         cursor.execute("UPDATE settings SET dbversion = '0.2'")
#         # base character table, one row per npc/category
#         cursor.execute("""
#             CREATE TABLE character (
#                 id INTEGER PRIMARY KEY, 
#                 name VARCHAR(64) NOT NULL,
#                 engine VARCHAR(64) NOT NULL,
#                 category TEXT CHECK( category IN ('npc', 'player', 'system')) NOT NULL DEFAULT 'npc'
#             )""")

#         # base engine configuration settings, things like language and voice
#         # these settings are in the context of a specific NPC.  Exactly which
#         # settings make sense depend on the engine, hence the key/value generic.
#         cursor.execute("""
#             CREATE TABLE base_tts_config (
#                 id INTEGER PRIMARY KEY,
#                 character_id INTEGER NOT NULL,
#                 key VARCHAR(64),
#                 value VARCHAR(64)
#             )
#         """)
#         cursor.execute("""
#             CREATE TABLE google_voices (
#                 id INTEGER PRIMARY KEY,
#                 name VARCHAR(64) NOT NULL,
#                 language_code VARCHAR(64) NOT NULL,
#                 ssml_gender VARCHAR(64) NOT NULL
#             )""")
#         cursor.execute("""
#             CREATE TABLE phrases (
#                 id INTEGER PRIMARY KEY,
#                 character_id INTEGER NOT NULL,
#                 text VARCHAR(256)
#             )
#         """)
#         cursor.execute("""
#             CREATE TABLE effects (
#                 id INTEGER PRIMARY KEY,
#                 character_id INTEGER NOT NULL,
#                 effect_name VARCHAR(256)
#             )
#         """)
#         cursor.execute("""
#             CREATE TABLE effect_setting (
#                 id INTEGER PRIMARY KEY,
#                 effect_id INTEGER NOT NULL,
#                 key VARCHAR(256) NOT NULL,
#                 value VARCHAR(256)
#             )
#         """)         
#         cursor.execute("""
#             CREATE TABLE hero_stat_events (
#                 id INTEGER PRIMARY KEY,
#                 hero INTEGER NOT NULL,
#                 event_time DATEIME NOT NULL,
#                 xp_gain INTEGER,
#                 inf_gain INTEGER
#             )
#         """)
#         cursor.execute("""
#             CREATE TABLE hero (
#                 id INTEGER PRIMARY KEY,
#                 name VARCHAR(256)
#             )
#         """)              
#         commit()        

def clean_customer_name(in_name):
    if in_name:
        clean_name = re.sub(r'[^\w]', '', in_name)
    else:
        clean_name = "GREAT_NAMELESS_ONE"

    if in_name is None:
        in_name = "GREAT NAMELESS ONE"

    return in_name, clean_name

def cache_filename(name, message):
    clean_message = re.sub(r'[^\w]', '', message)
    clean_message = hashlib.sha256(message.encode()).hexdigest()[:5] + f"_{clean_message[:10]}"
    return clean_message + ".mp3"