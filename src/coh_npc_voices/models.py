from datetime import datetime
import json
from sqlalchemy import DateTime, ForeignKey, Integer, String, create_engine, orm, select
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import Session
import logging
import sys
from typing import Optional
from sqlalchemy.orm import Mapped
import settings

logging.basicConfig(
    level=settings.LOGLEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("__name__")

engine = create_engine("sqlite:///voices.db", echo=False)

Base = declarative_base()

class Settings(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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

def get_character(name, category, session=None):
    log.info(f'/-- models.get_character({name=}, {category=}, {session=})')
    try:
        category=int(category)
    except ValueError:
        category=category_str2int(category)

    value = None

    if session is None:
        with Session(engine) as session:
            value = session.scalar(
                select(Character).where(
                    Character.name==name, 
                    Character.category==category
                )
            )
    else:
        log.debug('|- Using existing session')
        value = session.scalar(
            select(Character).where(
                Character.name==name,
                Character.category==category
            )
        )

    if value is None:
        log.info('|- Creating new character in database...')
        # this is the first time we've gotten a message from this
        # NPC, so they don't have a voice yet.  
        with Session(engine) as session:
            # default to the primary voice engine for this category of character
            value = Character(
                name=name,
                engine=settings.get_config_key(
                    f'{category}_engine_primary', settings.DEFAULT_ENGINE
                ),
                category=category,
            )
            session.add(value)
            session.commit()
            session.refresh(value)

    log.info(f'\\-- get_character() returning {value}')
    return value


def update_character_last_spoke(character, session=None):
    if session:
        character = session.scalars(
            select(Character).where(
                Character.id == character.id
            )
        ).first()

        character.last_spoke = datetime.now()
        session.commit()
    else:
        with Session(engine) as session:
            character = session.scalars(
                select(Character).where(
                    Character.id == character.id
                )
            ).first()
            character.last_spoke = datetime.now()
            session.commit()
        

class Character(Base):
    __tablename__ = "character"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    engine: Mapped[str] = mapped_column(String(64))
    category = mapped_column(Integer, index=True)
    last_spoke = mapped_column(DateTime, nullable=True)

    def cat_str(self):
        return ['', 'npc', 'player', 'system'][self.category]

    def __str__(self):
        return f"Character {self.category} {self.id}:{self.name} ({self.engine})"
    
    def __repr__(self):
        return f"<Character category={self.category!r} id={self.id!r} name={self.name!r} engine={self.engine!r}/>"

class BaseTTSConfig(Base):
    __tablename__ = "base_tts_config"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("character.id"))
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(String(64))

class GoogleVoices(Base):
    __tablename__ = "google_voices"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    language_code: Mapped[str] = mapped_column(String(64))
    ssml_gender: Mapped[str] = mapped_column(String(64))

    def __str__(self):
        return json.dumps(self.__dict__)

class ElevenLabsVoices(Base):
    __tablename__ = "eleven_labs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    voice_id: Mapped[str] = mapped_column(String(64))

    def __str__(self):
        return json.dumps(self.__dict__)    

class Phrases(Base):
    __tablename__ = "phrases"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("character.id"))
    text: Mapped[str] = mapped_column(String(256))
    ssml: Mapped[str] = mapped_column(String(512))

    def __repr__(self):
        return json.dumps({'id': self.id, 'character_id': self.character_id, 'text': self.text})

class Effects(Base):
    __tablename__ = "effects"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("character.id"))
    effect_name: Mapped[str] = mapped_column(String(256))

    def __repr__(self):
        return json.dumps({'id': self.id, 'character_id': self.character_id, 'effect_name': self.effect_name})

class EffectSetting(Base):
    __tablename__ = "effect_setting"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    effect_id: Mapped[int] = mapped_column(ForeignKey("effects.id"))
    key: Mapped[str] = mapped_column(String(256))
    value: Mapped[str] = mapped_column(String(256))

class Hero(Base):
    __tablename__ = "hero"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256))

class HeroStatEvent(Base):
    __tablename__ = "hero_stat_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hero_id = mapped_column(ForeignKey("hero.id"))
    event_time: orm.Mapped[datetime] 
    xp_gain: Mapped[Optional[int]]
    inf_gain: Mapped[Optional[int]]
