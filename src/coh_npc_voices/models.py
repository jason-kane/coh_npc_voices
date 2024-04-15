import enum
from datetime import datetime
import json
from sqlalchemy import Enum, ForeignKey, Integer, String, create_engine, orm, select, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import Session
import logging
import sys
from typing import Optional
from sqlalchemy.orm import Mapped
from typing_extensions import Annotated

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("__name__")

engine = create_engine("sqlite:///voices.db", echo=False)

Base = declarative_base()

intpk = Annotated[int, mapped_column(primary_key=True)]

class Settings(Base):
    __tablename__ = "settings"
    id: Mapped[intpk]
    logdir: Mapped[Optional[str]] = orm.mapped_column(String(256))


def get_settings():
    with Session(engine) as session:
        settings = session.scalars(
            select(Settings)
        ).first()
    
        if settings is None:
            log.warning('Settings not found!')
            settings = Settings(
                logdir = ""
            )
            session.add(settings)
            session.commit()

            settings = session.scalars(
                select(Settings)
            ).first()

        log.debug(dir(settings))
        return settings

def category_str2int(instr):
    try:
        return ['', 'npc', 'player', 'system'].index(instr)
    except ValueError:
        return -1

class Character(Base):
    __tablename__ = "character"
    id: Mapped[intpk]
    name: Mapped[str] = mapped_column(String(64))
    engine: Mapped[str] = mapped_column(String(64))
    category = mapped_column(Integer, index=True)

    def cat_str(self):
        return ['', 'npc', 'player', 'system'][self.category]

class BaseTTSConfig(Base):
    __tablename__ = "base_tts_config"
    id: Mapped[intpk]
    character_id: Mapped[intpk] = mapped_column(ForeignKey("character.id"))
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(String(64))

class GoogleVoices(Base):
    __tablename__ = "google_voices"
    id: Mapped[intpk]
    name: Mapped[str] = mapped_column(String(64))
    language_code: Mapped[str] = mapped_column(String(64))
    ssml_gender: Mapped[str] = mapped_column(String(64))

    def __str__(self):
        return json.dumps(self.__dict__)

class Phrases(Base):
    __tablename__ = "phrases"
    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[intpk] = mapped_column(ForeignKey("character.id"))
    text: Mapped[str] = mapped_column(String(256))
    ssml: Mapped[str] = mapped_column(String(512))

    def __repr__(self):
        return json.dumps({'id': self.id, 'character_id': self.character_id, 'text': self.text})

class Effects(Base):
    __tablename__ = "effects"
    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[intpk] = mapped_column(ForeignKey("character.id"))
    effect_name: Mapped[str] = mapped_column(String(256))

    def __repr__(self):
        return json.dumps({'id': self.id, 'character_id': self.character_id, 'effect_name': self.effect_name})

class EffectSetting(Base):
    __tablename__ = "effect_setting"
    id: Mapped[intpk]
    effect_id: Mapped[intpk] = mapped_column(ForeignKey("effects.id"))
    key: Mapped[str] = mapped_column(String(256))
    value: Mapped[str] = mapped_column(String(256))

class Hero(Base):
    __tablename__ = "hero"
    id: Mapped[intpk]
    name: Mapped[str] = mapped_column(String(256))

class HeroStatEvent(Base):
    __tablename__ = "hero_stat_events"
    id: Mapped[intpk]
    hero_id: Mapped[intpk] = mapped_column(ForeignKey("hero.id"))
    event_time: orm.Mapped[datetime] 
    xp_gain: Mapped[int]
    inf_gain: Mapped[int]
