import json
import logging
import os
import random
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

import settings
from npc import GROUP_ALIASES, PRESETS, add_group_alias_stub
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    create_engine,
    delete,
    orm,
    select,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, Session, mapped_column, scoped_session, sessionmaker

logging.basicConfig(
    level=settings.LOGLEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger(__name__)

engine = create_engine(
    "sqlite:///voices.db",
    echo=False,
    connect_args={'timeout': 2},
    isolation_level="AUTOCOMMIT",
)

@contextmanager
def db():
    #connection = engine.connect()
    session = scoped_session(
        sessionmaker(
            bind=engine,
            expire_on_commit=False
        )
    )
    yield session
    session.close()
    #connection.close()

Base = declarative_base()

class Settings(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    logdir: Mapped[Optional[str]] = orm.mapped_column(String(256))


class InvalidPreset(Exception):
    """Error in the preset"""

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

ENGINE_COSMETIC_TO_ID = {
    'Google Text-to-Speech': 'googletts',
    'Windows TTS': 'windowstts',
    'Eleven Labs': 'elevenlabs',
    'Amazon Polly': 'amazonpolly'
}

def get_character(name, category, session):
    log.info(f'/-- models.get_character({name=}, {category=}, {session=})')
    str_category = category
    try:
        category=int(category)
    except ValueError:
        category=category_str2int(category)

    value = None

    character = session.scalar(
        select(Character).where(
            Character.name==name, 
            Character.category==category
        )
    )

    if character is None:
        log.info(f'|- Creating new {str_category} character {name} in database...')
        # this is the first time we've gotten a message from this
        # NPC, so they don't have a voice yet.

        # first we need to find out if we have a preset for this category of foe.
        gender = None
        group_name = None
        preset = {}
        
        # look up this character by name
        if str_category == "npc":
            npc_spec = settings.get_npc_data(name)
            if npc_spec:
                gender = settings.get_npc_gender(name)
                group_name = npc_spec.get('group_name')
            else:
                gender = None
                group_name = None
            
            if group_name and group_name in GROUP_ALIASES:
                group_name = GROUP_ALIASES[group_name]
            
            preset = PRESETS.get(group_name, {})

        # based on the preset, and some random choices
        # where the preset does not specify, create a voice
        # for this NPC.

        # first we set the engine based on global defaults
        pkey = f'{str_category}_engine_primary'
        skey = f'{str_category}_engine_secondary'
        primary_engine_name = settings.get_config_key(pkey)
        secondary_engine_name = settings.get_config_key(skey)
        log.info(f"Primary engine ({pkey}): {primary_engine_name}")
        log.info(f"Secondary engine ({skey}): {secondary_engine_name}")

        # default to the primary voice engine for this category of character
        character = Character(
            name=name,
            engine=primary_engine_name,
            engine_secondary=secondary_engine_name,
            category=category,
        )
        session.add(character)
        session.commit()
        session.refresh(character)
        
        # now for the preset and/or random choices

        # start with some cleanup
        # wipe any existing effect configurations for this character
        for effect in session.scalars(
            select(Effects).where(
                Effects.character_id==character.id
            )
        ).all():
            session.execute(
                delete(EffectSetting).where(
                    EffectSetting.effect_id==effect.id
                )
            )

        for model in (BaseTTSConfig, Effects):
            session.execute(
                delete(model).where(
                    model.character_id == character.id
                )
            )

        engine_key = ENGINE_COSMETIC_TO_ID[primary_engine_name]
        rank = "primary"
        
        # if all_npc provided a gender, we will use that.
        if gender is None:
            # otherwise, use the gender value in preset.  If there isn't
            # one, fall back to a random choice.
            gender = preset.get('gender', random.choice(['Male', 'Female']))              

        # all of the available _engine_ configuration values
        engine_config_meta = session.scalars(
            select(EngineConfigMeta).where(
                EngineConfigMeta.engine_key==engine_key
            )
        ).all()

        log.info(f'|-  The configuration fields relevant to the {engine_key} TTS Engine are:')
        # None of these are in the DB yet, so this is a null-op
        # TODO: populate this db table
        for config_meta in engine_config_meta:
            log.info(f"|-    {config_meta}")
            # we want sensible defaults with some jitter
            # for each voice engine config setting.

            # TODO:  more varfunc types, Double and Boolean
            if config_meta.varfunc == "StringVar":
                # we don't know what the possible values
                # are since we can't run the function without
                # instantiating the engine, which will drag
                # in TK baggage.
                # but.. we can accesss the cache?.

                all_values = diskcache(f"{engine_key}_{config_meta.key}")
                
                if all_values is None:
                    log.warning(f'Cache {engine_key}_{config_meta.key} is empty')
                    value = "<Cache Failure>"
                else:
                    # it's a dict, keyey on voice_name
                    if gender and 'gender' in all_values[0].keys():
                        def gender_filter(voice):
                            return voice['gender'] == gender
                        all_values = filter(gender_filter, all_values)

                    # does the preset have any more guidance?
                    # use the preset if there is one.  Otherwise
                    # choose randomly from the available options.
                    log.info(f"{all_values=}")

                    if config_meta.key in preset:
                        value = preset[config_meta.key]
                    else:
                        chosen_row = random.choice(list(all_values))
                        log.info(f'Random selection: {chosen_row}')
                        value = chosen_row[config_meta.key]

            elif config_meta.varfunc == "DoubleVar":
                # no cache, use the preset or a random choice in the range.
                value = preset.get(
                    config_meta.key,
                    random.uniform(
                        config_meta.cfgdict['min'], 
                        config_meta.cfgdict['max']
                    )
                )

                # round to nearest multiple of 'resolution'
                resolution = config_meta.cfgdict.get('resolution', 1.0)
                value = round(
                    resolution * round(value / resolution)
                )

            elif config_meta.varfunc == "BooleanVar":
                # to be or not to be, that is the question.
                value = preset.get(
                    config_meta.key,
                    random.choice([True, False])
                )

            log.info(f'Configuring {rank} engine {engine_key}:  Setting {config_meta.key} to {value}')
            new_config_entry = BaseTTSConfig(
                character_id=character.id,
                rank=rank,
                key=config_meta.key,
                value=value
            )
            session.add(new_config_entry)
            session.commit()

        # add any effects
        for effect_dict in preset.get('Effects', []):
            # create the effect itself
            log.info(f'Adding effect: {effect_dict}')
            effect = Effects(
                character_id=character.id,
                effect_name=effect_dict['name']
            )
            session.add(effect)
            session.commit()
            session.refresh(effect)

            # add the settings      
            for key, value in effect_dict.items():
                # we've already baked the name field
                if key == "name":
                    continue

                effect_settings = EffectSetting(
                    effect_id=effect.id,
                    key=key,
                    value=value
                )
                session.add(effect_settings)
            session.commit()

    log.info(f'\\-- get_character() returning {character}')
    return character


def get_character_from_rawname(raw_name, session):
    try:
        category, name = raw_name.split(maxsplit=1)
    except ValueError:
        log.error('Invalid character raw_name: %s', raw_name)
        return None

    return get_character(name, category, session)


def update_character_last_spoke(character, session):
    character = session.scalars(
        select(Character).where(
            Character.id == character.id
        )
    ).first()
    character.last_spoke = datetime.now()       


class EngineConfigMeta(Base):
    __tablename__ = "engine_config_meta"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    engine_key: Mapped[str] = mapped_column(String(64))
    cosmetic: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(64))
    varfunc: Mapped[str] = mapped_column(String(64))
    default: Mapped[str] = mapped_column(String(64))
    cfgdict: Mapped[JSON] = mapped_column(type_=JSON, nullable=False)
    # must be a self.gatherfunc() callable by the engine
    gatherfunc: Mapped[Optional[str]] = mapped_column(String(64))

    def __str__(self):
        return f"<EngineConfigMeta {self.engine_key=}, {self.cosmetic=}, {self.key=}, {self.varfunc=}, {self.default=}, {self.cfgdict=}, {self.gatherfunc=}/>"


class Character(Base):
    __tablename__ = "character"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    engine: Mapped[str] = mapped_column(String(64))
    engine_secondary: Mapped[str] = mapped_column(String(64))
    category: Mapped[int] = mapped_column(Integer, index=True)
    last_spoke: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

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
    log.info(f'diskcache({key=}, {value=})')
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


def get_engine_config(character_id, rank):
    out = {}
    with Session(engine) as session:
        items = session.scalars(
            select(BaseTTSConfig).where(
                BaseTTSConfig.character_id == character_id,
                BaseTTSConfig.rank == rank
            )
        ).all()

        for row in items:
            out[row.key] = row.value

    return out

def set_engine_config(character_id, rank, new_config):
    """
    Generally speaking -- only one thing is actually changing, because this is called in the listeners on the config widgets.
    that is what makes returning 'change' not stupid.  The most common multi-config setting change happens when the user switches
    to a different TTS enigne.  That part isn't our concern.   
    """
    change = None
    old_config = get_engine_config(character_id, rank)
    log.info(f"{character_id=} {old_config=} {new_config=}")
    with Session(engine) as session:
        for key in new_config:   
            if key in old_config:
                if old_config[key] != new_config[key]:
                    log.info(f'change in {key}: {old_config[key]} != {new_config[key]}')
                    # this value has changed
                    row = session.scalar(
                        select(BaseTTSConfig).where(
                            BaseTTSConfig.character_id == character_id,
                            BaseTTSConfig.rank == rank,
                            BaseTTSConfig.key == key
                    ))
                    if row:
                        log.info(f'Changing value of {row} to {new_config[key]}')
                        row.value = new_config[key]
                        change = key
                        session.commit()
                    else:
                        log.info(f'Charactger {character_id} has no previous engine config for {rank} {key}')
                        row = BaseTTSConfig(
                            character_id=character_id,
                            rank=rank,
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
                    rank=rank,
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
                        BaseTTSConfig.rank == rank,
                        BaseTTSConfig.key == key
                    )
                )

        session.commit()
        return change


class BaseTTSConfig(Base):
    __tablename__ = "base_tts_config"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("character.id"))
    rank: Mapped[str] = mapped_column(String(32)) 
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(String(64))
    
    def __repr__(self):
        return f"<BaseTTSConfig {self.id} {self.character_id=} {self.rank=} {self.key=} {self.value=}/>"

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
