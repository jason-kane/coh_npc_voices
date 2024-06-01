import logging
import os
import random
import re

import effects
import engines
import models
import settings
from npc import GROUP_ALIASES, PRESETS, add_group_alias_stub
from pedalboard.io import AudioFile
from sqlalchemy import delete, select
from voicebox.sinks import Distributor, SoundDevice, WaveFile

log = logging.getLogger(__name__)

PLAYER_CATEGORY = models.category_str2int("player")

# act like this is a tk.var
class tkvar_ish:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value


def apply_preset(character_name, character_category, preset_name, gender=None):
    preset = PRESETS.get(GROUP_ALIASES.get(preset_name, preset_name))
    
    if gender is None:
        gender = settings.get_npc_gender(character_name)

    if preset is None or len(preset) == 0:
        log.info(f'No preset is available for {preset_name}')
        add_group_alias_stub(preset_name)
        preset = PRESETS.get(GROUP_ALIASES.get(preset_name, preset_name))

    with models.db() as session:
        log.info('Applying preset: %s', preset)
        character = models.get_character(
            character_name,
            character_category,
            session=session
        )
       
        # TODO: WTF?
        if character_category == 2:
            default = settings.get_config_key('DEFAULT_PLAYER_ENGINE')
        else:
            default = settings.get_config_key('DEFAULT_ENGINE')

        if preset['engine'] == 'any':
            character.engine = default
        else:
            character.engine = preset['engine']

        session.commit()
        
        for model in ("BaseTTSConfig", "Effects"):
            # wipe any existing entries for this character
            session.execute(
                delete(getattr(models, model)).where(
                    getattr(models, model).character_id == character.id
                )
            )
        
        # This is wrong.  we're only setting config for the fields that have values.
        for key in preset['BaseTTSConfig']:
            log.info(f'key: {key}, value: {preset["BaseTTSConfig"][key]}')
            value = preset['BaseTTSConfig'][key]

            if key == "voice_name" and len(value) == 2:
                # I know, sloppy.  what happens if there is a two character
                # voice installed and used as a preset?
                if gender:
                    # we have a gender override, probably from
                    # all_npcs.json
                    choice, default_gender = preset['BaseTTSConfig'][key]
                    if "FEMALE" in gender.upper():
                        gender="Female"
                    elif "MALE" in gender.upper():
                        gender="Male"
                    else:
                        gender = default_gender
                    
                else:
                    choice, gender = preset['BaseTTSConfig'][key]

                if choice == "random":
                    if gender == "any":
                        gender = None
                    
                    all_available_names = engines.get_engine(
                        character.engine,
                        session
                    ).get_voice_names(
                        gender=gender
                    )
                    log.info(f'Choosing a random voice from {all_available_names}')
                    value = random.choice(all_available_names)
                    log.info(f'Selected voice: {value}')
                else:
                    log.error(f'Unknown variable preset setting: {choice}')   

            log.info(f'Adding new BaseTTSConfig for {key} => {value}')
            session.add(
                models.BaseTTSConfig(
                    character_id=character.id,
                    key=key,
                    value=value
                )
            )
        
        # TODO
        # we aren't cleaning up old effectsettings, so they database is going to
        # very gradually bloat with unreachable objects.
        if 'Effects' in preset:
            # wipe any existing effects
            session.execute(
                delete(models.Effects).where(
                    models.Effects.character_id == character.id
                )
            )

        for effect_name in preset.get('Effects', []):
            effect = models.Effects(
                character_id=character.id,
                effect_name=effect_name
            )
            session.add(effect)

            # we need the effect.id
            session.commit()
            session.refresh(effect)

            for effect_setting_key in preset['Effects'][effect_name]:
                value = preset['Effects'][effect_name][effect_setting_key]
                
                session.add(
                    models.EffectSetting(
                        effect_id=effect.id,
                        key=effect_setting_key,
                        value=str(value)
                    )
                )

        session.commit()

# I'm actually a little curious to see exactly how this will behave.  From npcChatter this is being called in
# a subprocess, but when the editor triggers it we are in a thread.  The thread dies, the new thread doesn't know
# ENGINE_OVERRIDE has been triggered and we keep smacking elevenlabs even though we've run out of credits.

ENGINE_OVERRIDE = {}

def create(character, message, cachefile):
    """
    This NPC exists in our database but we don't
    have this particular message rendered.

    This is how npc_chatter talks.  editor has its own seperate-but=equal
    version of this, they should really be merged. (WIP)

    1. Get vocal characteristics from sqlite using 
       the npc_id
    2. Render message based on that data
    3. persist as an mp3 in cachefile
    """
    global ENGINE_OVERRIDE
    log.info(f'voice_builder.create({character=}, {message=}, {cachefile=})')
    
    with models.db() as session:
        voice_effects = session.scalars(
            select(models.Effects).where(
                models.Effects.character_id == character.id
            )
        ).all()
    
    effect_list = []
    for effect in voice_effects:
        log.info(f'Adding effect {effect} found in the database')
        effect_class = effects.EFFECTS[effect.effect_name]
        effect_instance = effect_class(None)

        effect_instance.effect_id.set(effect.id)
        effect_instance.load()  # load the DB config for this effect

        effect_list.append(effect_instance.get_effect())

    # have we seen this particular phrase before?
    if character.category != PLAYER_CATEGORY or settings.PERSIST_PLAYER_CHAT:
        # we want to collect and persist these to enable the editor to
        # rebuild them, replacing the mp3 in cache.
        with models.db() as session:
            phrase = session.execute(
                select(models.Phrases).where(
                    models.Phrases.character_id == character.id,
                    models.Phrases.text == message
                )
            ).first()
            
        log.debug(phrase)

        if phrase is None:
            log.info('Phrase not found.  Creating...')
            # it does not exist, now it does.
            with models.db() as session:
                phrase = models.Phrases(
                    character_id=character.id,
                    text=message,
                    ssml=""
                )
                session.add(phrase)
                session.commit()

        try:
            clean_name = re.sub(r'[^\w]', '',character.name)
            os.mkdir(os.path.join("clip_library", character.cat_str(), clean_name))
        except OSError:
            # the directory already exists.  This is not a problem.
            pass

        sink = Distributor([
            SoundDevice(),
            WaveFile(cachefile + '.wav')
        ])
        save = True
    else:
        sink = Distributor([
            SoundDevice()
        ])
        save = False 
    
    selected_name = tkvar_ish(f"{character.cat_str()} {character.name}")
    
    rank = 'primary'
    if ENGINE_OVERRIDE.get(character.engine, False):
        rank = 'secondary'


    # character.engine may already have a value.  It probably does.  We're over-writing it
    # with anything we have in the dict ENGINE_OVERRIDE.  But if we don't have anything, you can keep
    # your previous value and carry on.

    try:
        if rank == 'secondary':
            raise engines.USE_SECONDARY
        
        log.info(f'Using engine: {character.engine}')
        engines.get_engine(character.engine)(None, 'primary', selected_name).say(message, effect_list, sink=sink)
    except engines.USE_SECONDARY:
        # our chosen engine for this character isn't working.  So we're going to switch
        # to the secondary and use that for the rest of this session.
        ENGINE_OVERRIDE[character.engine] = True

        if character.engine_secondary:
            # use the secondary engine config defined for this character
            engine_instance = engines.get_engine(character.engine_secondary)
            engine_instance(None, 'secondary', selected_name).say(message, effect_list, sink=sink)
        else:
            # use the global default secondary engine
            engine_name = settings.get_config_key(f"{character.category}_engine_secondary")
            engine_instance = engines.get_engine(engine_name)
            engine_instance(None, 'secondary', selected_name).say(message, effect_list, sink=sink)
     
    if save:
        with AudioFile(cachefile + ".wav") as input:
            with AudioFile(
                filename=cachefile,
                samplerate=input.samplerate,
                num_channels=input.num_channels
            ) as output:
                while input.tell() < input.frames:
                    retries = 5
                    success = False
                    while not success and retries > 0:
                        try:
                            output.write(input.read(1024))
                            success = True
                        except RuntimeError as err:
                            log.errror(err)
                        retries -= 1
                    
            log.info(f'Created {cachefile}')

        os.unlink(cachefile + ".wav")
