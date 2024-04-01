import logging
import os
import re

from pedalboard.io import AudioFile
from voicebox.sinks import Distributor, SoundDevice, WaveFile

import effects
from db import commit, get_cursor
from engines import get_engine

log = logging.getLogger("__name__")

MESSAGE_CATEGORIES = ['npc', 'system', 'player']

default_engine = "Windows TTS"

# act like this is a tk.var
class tkvar_ish:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value

def create(character_id, message, cachefile):
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
    cursor = get_cursor()
    name, engine_name, category = cursor.execute(
        "select name, engine, category from character where id=?", 
        (character_id, )
    ).fetchone()
    engine = get_engine(engine_name)
    
    # how about a list of audio effects this stream should be 
    # passed through first?
    voice_effects = cursor.execute("""
        SELECT 
            id, effect_name
        FROM
            effects
        where
            character_id = ?
    """, (
        character_id,
    )).fetchall()

    effect_list = []
    for effect in voice_effects:
        log.info(f'Adding effect {effect} found in the database')
        id, effect_name = effect
        effect_class = effects.EFFECTS[effect_name]

        effect = effect_class()

        effect_setting = cursor.execute("""
            SELECT 
                key, value
            FROM
                effect_setting
            where
                effect_id = ?
        """, (
            id,
        )).fetchall()

        # reach into effect() and set the values this
        # plugin expects.
        for key, value in effect_setting:
            tkvar = getattr(effect, key, None)
            if tkvar:
                tkvar.set(value)
            else:
                log.error(f'Invalid configuration.  {key} is not available for {effect}')

        effect_list.append(effect)

    # have we seen this particular phrase before?
    phrase = cursor.execute("""
        SELECT id FROM phrases WHERE character_id=? AND text=?
    """, (character_id, message)).fetchone()
    if phrase is None:
        # it does not exist, now it does.
        cursor.execute("""
            INSERT INTO phrases (character_id, text) VALUES (?, ?)
        """, (character_id, message))
        commit()

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
                output.write(input.read(1024))
        log.info(f'Created {cachefile}')

    #audio = pydub.AudioSegment.from_wav(cachefile + ".wav")
    #audio.export(cachefile, format="mp3")
    os.unlink(cachefile + ".wav")
