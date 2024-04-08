import enum
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, String, create_engine, orm, select
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import Session
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("__name__")

engine = create_engine("sqlite:///voices.db", echo=True)

Base = declarative_base()
metadata = Base.metadata

class Settings(Base):
    __tablename__ = "settings"
    id = mapped_column(Integer, primary_key=True)
    logdir = orm.mapped_column(String(256))


def get_settings():
    with Session(engine) as session:
        settings = session.query(
            Settings
        ).first()
    
        if settings is None:
            log.warning('Settings not found!')
            settings = Settings(
                logdir = ""
            )
            session.add_all([settings])
            session.commit()

        log.info(dir(settings))
        return settings


class CharacterCategories(enum.Enum):
    npc = 1
    player = 2
    system = 3


class Character(Base):
    __tablename__ = "character"
    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(64))
    engine = mapped_column(String(64))
    category = Enum(CharacterCategories)

class BaseTTSConfig(Base):
    __tablename__ = "base_tts_config"
    id = mapped_column(Integer, primary_key=True)
    character_id = mapped_column(ForeignKey("character.id"))
    key = mapped_column(String(64))
    value = mapped_column(String(64))

class GoogleVoices(Base):
    __tablename__ = "google_voices"
    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(64))
    language_code = mapped_column(String(64))
    ssml_gender = mapped_column(String(64))

class Phrases(Base):
    __tablename__ = "phrases"
    id = mapped_column(Integer, primary_key=True)
    character_id = mapped_column(ForeignKey("character.id"))
    text = mapped_column(String(256))

class Effects(Base):
    __tablename__ = "effects"
    id = mapped_column(Integer, primary_key=True)
    character_id = mapped_column(ForeignKey("character.id"))
    effect_name = mapped_column(String(256))

class EffectSetting(Base):
    __tablename__ = "effect_setting"
    id = mapped_column(Integer, primary_key=True)
    effect_id = mapped_column(ForeignKey("effects.id"))
    key = mapped_column(String(256))
    value = mapped_column(String(256))

class Hero(Base):
    __tablename__ = "hero"
    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(256))

class HeroStatEvent(Base):
    __tablename__ = "hero_stat_events"
    id = mapped_column(Integer, primary_key=True)
    hero_id = mapped_column(ForeignKey("hero.id"))
    event_time: orm.Mapped[datetime] = mapped_column()
    xp_gain = mapped_column(Integer)
    inf_gain = mapped_column(Integer)
