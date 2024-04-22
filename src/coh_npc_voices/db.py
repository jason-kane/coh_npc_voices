import logging
import sys
import re
import hashlib

from sqlalchemy import create_engine
from sqlalchemy_utils import database_exists, create_database
import models

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
        models.Base.metadata.create_all(engine)
    return

if not database_exists(engine.url):
    build_migrate()


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