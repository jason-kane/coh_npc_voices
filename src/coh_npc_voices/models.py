from datetime import datetime
import json
from sqlalchemy import DateTime, ForeignKey, Integer, String, create_engine, orm, select, delete
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import mapped_column
import os
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


def get_character_from_rawname(raw_name, session=None):
    try:
        category, name = raw_name.split(maxsplit=1)
    except ValueError:
        log.error('Invalid character raw_name: %s', raw_name)
        return None

    return get_character(name, category, session=session)


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
    engine_secondary: Mapped[str] = mapped_column(String(64))
    category = mapped_column(Integer, index=True)
    last_spoke = mapped_column(DateTime, nullable=True)

    def cat_str(self):
        return ['', 'npc', 'player', 'system'][self.category]

    def __str__(self):
        return f"Character {self.category} {self.id}:{self.name} ({self.engine})"
    
    def __repr__(self):
        return f"<Character category={self.category!r} id={self.id!r} name={self.name!r} engine={self.engine!r}/>"


CACHE_DIR = 'cache'
def diskcache(key, value=None):
    """
    key must be valid as a base filename
    value must be None or a json-able object
    """
    filename = os.path.join(CACHE_DIR, key + ".json")
    if value is None:
        if os.path.exists(filename):
            with open(filename, 'rb') as h:
                content =json.loads(h.read())
            return content
    else:
        if not os.path.exists(CACHE_DIR):
            os.mkdir(CACHE_DIR)

        with open(filename, 'w') as h:
            h.write(json.dumps(value, indent=2))
        
        return value


def get_engine_config(character_id):
    out = {}
    with Session(engine) as session:
        items = session.scalars(
            select(BaseTTSConfig).where(
                character_id == character_id
            )
        ).all()

        for row in items:
            out[row.key] = row.value

    return out

def set_engine_config(character_id, new_config):
    """
    Generally speaking -- only one thing is actually changing, because this is called in the listeners on the config widgets.
    that is what makes returning 'change' not stupid.  The most common multi-config setting change happens when the user switches
    to a different TTS enigne.  That part isn't our concern.   
    """
    change = None
    old_config = get_engine_config(character_id)
    log.info(f"{character_id=} {old_config=} {new_config=}")
    with Session(engine) as session:
        for key in new_config:   
            if key in old_config:
                if old_config[key] != new_config[key]:
                    log.info(f'change in {key}: {old_config[key]} != {new_config[key]}')
                    # this value has changed
                    row = session.scalar(
                        select(BaseTTSConfig).where(
                            BaseTTSConfig.character_id == character_id
                        ).where(
                            BaseTTSConfig.key == key
                        )
                    )
                    if row:
                        log.info(f'Changing value of {row} to {new_config[key]}')
                        row.value = new_config[key]
                        change = key
                        session.commit()
                    else:
                        log.info(f'Charactger {character_id} has no previous engine config for {key}')
                        row = BaseTTSConfig(
                            character_id=character_id,
                            key=key,
                            value=new_config[key]
                        )
                        session.add(row)        
            else:
                # we have a new key/value, this will only 
                # happen when upgrading/downgrading.
                log.info(f'new key: {key} = {new_config[key]}')
                row = BaseTTSConfig(
                    character_id=character_id,
                    key=key,
                    value=new_config[key]
                )
                change = key
                session.add(row)

        for key in old_config:
            if key not in new_config:
                # this key is no longer part of the config, this
                # will also only happen when upgrading/downgrading.
                row = session.execute(
                    delete(BaseTTSConfig).where(
                        BaseTTSConfig.character_id == character_id,
                        BaseTTSConfig.key == key
                    )
                )

        session.commit()
        return change


class BaseTTSConfig(Base):
    __tablename__ = "base_tts_config"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("character.id"))
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(String(64))
    
    def __repr__(self):
        return f"<BaseTTSConfig {self.id} {self.character_id=} {self.key=} {self.value=}/>"

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
