
import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import alembic.config
import cnv.database.models as models
from sqlalchemy import create_engine
from sqlalchemy_utils import create_database, database_exists

engine = create_engine("sqlite:///voices.db", echo=True)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger(__name__)

alembic_ini = os.path.abspath(
    os.path.join(
        os.path.dirname(
            os.path.realpath(__file__)
        ), 
    '..', 'alembic.ini')
)

alembicArgs = [
    '-c',
    alembic_ini,
    '--raiseerr',
    'upgrade', 
    'head',
]

@contextmanager
def set_directory(path: Path):
    """
    Sets the cwd within the context
    https://dev.to/teckert/changing-directory-with-a-python-context-manager-2bj8

    Args:
        path (Path): The path to the cwd

    Yields:
        None
    """

    origin = Path().absolute()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(origin)

def build_migrate():
    # it really doesn't exist.
    if not database_exists(engine.url):    
        create_database(engine.url)
        models.Base.metadata.create_all(engine)    
    return

if not database_exists(engine.url):
    build_migrate()
    # a default character entry makes everything a little easier.
    with models.Session(models.engine) as session:
        default = models.Character(
            name="default",
            engine="Windows TTS",
            engine_secondary="Windows TTS",
            category=3
        )
        session.add(default)
        session.commit()

log.info('Checking for database migration...')
alembic.config.main(argv=alembicArgs)
