import json
import logging
import random
import re
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Self

import pyfiglet
from cnv.lib import settings
from cnv.lib.settings import diskcache
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
from sqlalchemy.engine.interfaces import Connectable
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

class InvalidPreset(Exception):
    """Error in the preset"""

def category_str2int(instr):
    try:
        return ['', 'npc', 'player', 'system'].index(instr)
    except ValueError:
        return -1
    
def category_int2str(inint):
    try:
        return ['', 'npc', 'player', 'system'][inint]
    except ValueError:
        return ''

ENGINE_COSMETIC_TO_ID = {
    'Google Text-to-Speech': 'googletts',
    'Windows TTS': 'windowstts',
    'Eleven Labs': 'elevenlabs',
    'Amazon Polly': 'amazonpolly'
}

language_code_regex = "en-.*"

class Character(Base):
    __tablename__ = "character"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    engine: Mapped[str] = mapped_column(String(64))
    engine_secondary: Mapped[str] = mapped_column(String(64))
    category: Mapped[int] = mapped_column(Integer, index=True)
    last_spoke: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    group_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    def cat_str(self):
        return ['', 'npc', 'player', 'system'][self.category]

    def __str__(self):
        return f"Character {self.category} {self.id}:{self.name} ({self.engine})"
    
    def __repr__(self):
        return f"<Character category={self.category!r} id={self.id!r} name={self.name!r} engine={self.engine!r}/>"

    @classmethod
    def create_character(cls, name: str, category: int, session: Connectable) -> Self:
        # go big or go home, right?
        str_category = category_int2str(category)

        log.info("\n" + pyfiglet.figlet_format(f'New {str_category}', font="3d_diagonal", width=120))
        log.debug("\n" + pyfiglet.figlet_format(name, font="3d_diagonal", width=120))
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
            
            if group_name:
                group_name = settings.get_alias(group_name)               
            
            preset = settings.get_preset(group_name)

        # based on the preset, and some random choices
        # where the preset does not specify, create a voice
        # for this NPC.

        # first we set the engine based on global defaults
        pkey = f'{str_category}_engine_primary'
        skey = f'{str_category}_engine_secondary'
        primary_engine_name = settings.get_config_key(pkey)
        secondary_engine_name = settings.get_config_key(skey)
        log.debug(f"Primary engine ({pkey}): {primary_engine_name}")
        log.debug(f"Secondary engine ({skey}): {secondary_engine_name}")

        # default to the primary voice engine for this category of character
        character = cls(
            name=name,
            engine=primary_engine_name,
            engine_secondary=secondary_engine_name,
            category=category,
        )
        session.add(character)
        session.commit()
        session.refresh(character)
        
        # now for the preset and/or random choices
        engine_key = ENGINE_COSMETIC_TO_ID[primary_engine_name]
        rank = "primary"
        
        # if all_npc provided a gender, we will use that.
        if gender is None:
            # otherwise, use the gender value in preset.  IE: the preset gender
            # changes the default if all_npcs doesn't say otherwise.
            #
            # fall back to a random choice.
            gender = preset.get('gender', None)
            if gender is None:
                if name in ["Celestine", "Alessandra", ]:
                    gender = 'Female'
                else:
                    gender = random.choice(['Male', 'Female'])

        # all of the available _engine_ configuration values
        engine_config_meta = session.scalars(
            select(EngineConfigMeta).where(
                EngineConfigMeta.engine_key==engine_key
            )
        ).all()

        log.debug(f'|-  The configuration fields relevant to the {engine_key} TTS Engine are:')
        # loop through the availabe configuration settings
        for config_meta in engine_config_meta:
            log.debug(f"|-    {config_meta}")
            # we want sensible defaults with some jitter
            # for each voice engine config setting.
            value = None

            # does this configuration setting take a string value from a list of
            # possible choices?
            if config_meta.varfunc == "StringVar":
                # we don't know what the possible values are since we can't run
                # the function without instantiating the engine, which will drag
                # in TK baggage. 

                # but.. we can accesss the cache?.  does that introduce a
                # sequence dependency?
                all_values = diskcache(f"{engine_key}_{config_meta.key}")
                
                if all_values is None:
                    log.warning(f'Cache {engine_key}_{config_meta.key} is empty')
                    value = "<Cache Failure>"
                else:
                    # it's a dict, keyey on voice_name
                    # language_code_regex = "en-.*"
                    if language_code_regex and 'language_code' in all_values[0].keys():
                        # pass through languages that satisfy the regex
                        out = []
                        for v in all_values:
                            code = v.get('language_code', '')
                            if re.match(language_code_regex, code):
                                out.append(v)
                        all_values = out
                    
                    # if we have a gender, filter out the voices that don't
                    # have the same gender.
                    if gender and 'gender' in all_values[0].keys():
                        def gender_filter(voice):
                            return voice['gender'] == gender
                        all_values = filter(gender_filter, all_values)

                    # does the preset have any more guidance?
                    # use the preset if there is one.  Otherwise
                    # choose randomly from the available options.
                    log.debug(f"{all_values=}")

                    if config_meta.key in preset:
                        value = preset[config_meta.key]
                    else:
                        chosen_row = random.choice(list(all_values))
                        log.debug(f'Random selection: {chosen_row}')
                        value = chosen_row[config_meta.key]

            # do we have a numeric value, with a min/max and some
            # hints about useful granularity?
            elif config_meta.varfunc == "DoubleVar":
                # no cache, use the preset or a random choice in the range.
                # this shouldn't be .uniform, it should be more likely 
                # for the values that are more common.
                value = preset.get(
                    config_meta.key,
                    random.uniform(
                        config_meta.cfgdict['min'], 
                        config_meta.cfgdict['max']
                    )
                )

                # round to nearest multiple of 'resolution'
                resolution = config_meta.cfgdict.get('resolution', 1.0)
                value = (
                    resolution * round(value / resolution)
                )

            # do we have a true/false, enable/disable sort thing?
            elif config_meta.varfunc == "BooleanVar":
                # to be or not to be, that is the question.
                value = preset.get(
                    config_meta.key,
                    random.choice([True, False])
                )

            # write our value for this configuration setting to the database
            log.info(f'Configuring {rank} engine {engine_key}:  Setting {config_meta.key} to {value}')
            new_config_entry = BaseTTSConfig(
                character_id=character.id,
                rank=rank,
                key=config_meta.key,
                value=value
            )
            session.add(new_config_entry)
            session.commit()

        # add effects but only if there is a preset, no random effects.
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

        return character

    @classmethod
    def get(cls, name: str, category: int, session: Connectable) -> Self:
        """
        Retrieve an existing character from the database, or (if they do not exist)
        create a new character database entry and return that.

        Return value is a Character() object.
        """
        log.debug(f'/-- Character.get({name=}, {category=}, session=...)')
        
        try:
            category=int(category)
        except ValueError:
            category=category_str2int(category)

        character = session.scalar(
            select(Character).where(
                Character.name==name, 
                Character.category==category
            )
        )

        if character is None:
            character = cls.create_character(
                name, category, session
            )

        log.debug(f'\\-- Character.get() returning {character}')
        return character


def get_character_from_rawname(raw_name, session):
    log.error(f'OBSOLETE get_character_from_rawname({raw_name=}, {session=})')
    # use Character.get()
    if raw_name is None:
        return
    
    try:
        category, name = raw_name
    except ValueError:
        settings.how_did_i_get_here()
        log.error(f'Invalid character {raw_name=}')
        return None

    return Character.get(name, category, session)


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


def get_engine_config(character_id, rank):
    out = {}
    with Session(engine) as session:
        items = session.scalars(
            select(BaseTTSConfig).where(
                BaseTTSConfig.character_id == character_id,
                BaseTTSConfig.rank == rank
            )
        ).all()
        
        if items is None:
            log.info(f'Did not find any engine configuration for {character_id=} {rank=}')

        for row in items:
            out[row.key] = row.value

    log.info(f"{character_id=} {rank=} {out=}")
    return out

def set_engine_config(character_id, rank, new_config):
    """
    """
    old_config = get_engine_config(character_id, rank)
    # log.info(pyfiglet.figlet_format("Engine Edit", font="3d_diagonal", width=120))
    log.info(f"Setting Engine Config: {character_id=} {old_config=} {new_config=}")
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
                    log.debug(f'The value of {key} has not changed (still {new_config[key]})')
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

    def __repr__(self):
        return json.dumps({'id': self.id, 'character_id': self.character_id, 'text': self.text})

class Translation(Base):
    __tablename__ = "translations"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phrase_id: Mapped[int] = mapped_column(ForeignKey("phrases.id"))
    language_code: Mapped[Optional[str]] = mapped_column(String(2))

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
