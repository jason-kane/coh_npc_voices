import logging
import os
import re

import db
import effects
import random
import models
import engines
from pedalboard.io import AudioFile
from sqlalchemy import select, update
from voicebox.sinks import Distributor, SoundDevice, WaveFile
from sqlalchemy import delete, exc, select, update
from npc import PRESETS, GROUP_ALIASES

log = logging.getLogger("__name__")

default_engine = "Windows TTS"

# act like this is a tk.var
class tkvar_ish:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value

def apply_preset(character, preset_name, gender=None):
    preset = PRESETS.get(GROUP_ALIASES.get(preset_name, preset_name))
    
    if preset is None:
        log.info(f'No preset is available for {preset_name}')
        return

    with models.Session(models.engine) as session:
        character.engine = preset['engine']
        
        for model in ("BaseTTSConfig", "Effects"):
            # wipe any existing entries for this character
            session.execute(
                delete(getattr(models, model)).where(
                    getattr(models, model).character_id == character.id
                )
            )
        
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
                        gender="female"
                    elif "MALE" in gender.upper():
                        gender="male"
                    else:
                        gender = default_gender
                    
                else:
                    choice, gender = preset['BaseTTSConfig'][key]

                if choice == "random":
                    if gender == "any":
                        gender = None

                    all_available_names = engines.get_engine(
                        character.engine
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


def create(character, message, cachefile):
    """
    This NPC exists in our database but we don't
    have this particular message rendered.

    This is how npc_chatter talks.  editor has its own seperate-but=equal
    version of this, they should really be merged.

    1. Get vocal characteristics from sqlite using 
       the npc_id
    2. Render message based on that data
    3. persist as an mp3 in cachefile
    """
    with models.Session(models.engine) as session:
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

        with models.Session(models.engine) as session:
            effect_settings = session.scalars(
                select(models.EffectSetting).where(
                    models.EffectSetting.effect_id == effect.id
                )
            ).all()

        # reach into effect() and set the values this
        # plugin expects.
        for effect_setting in effect_settings:
            tkvar = getattr(effect, effect_setting.key, None)
            if tkvar:
                tkvar.set(effect_setting.value)
            else:
                log.error(f'Invalid configuration.  {effect_setting.key} is not available for {effect}')

        effect_list.append(effect_instance.get_effect())

    # have we seen this particular phrase before?
    with models.Session(models.engine) as session:
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
    
    selected_name = tkvar_ish(f"{character.cat_str()} {character.name}")

    engines.get_engine(character.engine)(None, selected_name).say(message, effect_list, sink=sink)

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

    #audio = pydub.AudioSegment.from_wav(cachefile + ".wav")
    #audio.export(cachefile, format="mp3")
    os.unlink(cachefile + ".wav")
