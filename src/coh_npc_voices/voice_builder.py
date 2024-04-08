import logging
import os
import re

import db
import effects
import models
from engines import get_engine
from pedalboard.io import AudioFile
from voicebox.sinks import Distributor, SoundDevice, WaveFile

log = logging.getLogger("__name__")

MESSAGE_CATEGORIES = ['npc', 'system', 'player']

default_engine = "Windows TTS"

# act like this is a tk.var
class tkvar_ish:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value

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
        voice_effects = session.query(
            models.Effects
        ).filter(
            character_id=character.id
        ).fetchall()
    
    effect_list = []
    for effect in voice_effects:
        log.info(f'Adding effect {effect} found in the database')
        effect_class = effects.EFFECTS[effect.name]

        effect = effect_class(None)

        with models.Session(models.engine) as session:
            effect_settings = session.query(
                models.EffectSetting
            ).filter_by(effect_id=effect.id)

        # reach into effect() and set the values this
        # plugin expects.
        for effect_setting in effect_settings:
            tkvar = getattr(effect, effect_setting.key, None)
            if tkvar:
                tkvar.set(effect_setting.value)
            else:
                log.error(f'Invalid configuration.  {effect_setting.key} is not available for {effect}')

        effect_list.append(effect.get_effect())

    # have we seen this particular phrase before?
    with models.Session(models.engine) as session:
        phrase = session.query(
            models.Phrases
        ).filter_by(
            character_id=character.id,
            text=message
        ).one_or_none()

        if phrase is None:
            # it does not exist, now it does.
            phrase = models.Phrases(
                character_id=character.id,
                text=message
            )
            session.add(phrase)
            session.commit()

    try:
        clean_name = re.sub(r'[^\w]', '', name)
        os.mkdir(os.path.join("clip_library", category, clean_name))
    except OSError:
        # the directory already exists.  This is not a problem.
        pass

    sink = Distributor([
        SoundDevice(),
        WaveFile(cachefile + '.wav')
    ])
    
    selected_name = tkvar_ish(f"{category} {name}")

    engine(None, selected_name).say(message, effect_list, sink=sink)

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
