from voicebox.sinks import Distributor, SoundDevice, WaveFile
import pydub
import os
import re
from engines import get_engine


MESSAGE_CATEGORIES = ['npc', 'system', 'player']

default_engine = "Windows TTS"

class tkvar_ish:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value

def create(con, character_id, message, cachefile):
    """
    This NPC exists in our database but we don't
    have this particular message rendered.

    1. Get vocal characteristics from sqlite using 
       the npc_id
    2. Render message based on that data
    3. persist as an mp3 in cachefile
    """
    cursor = con.cursor()
    name, engine_name, category = cursor.execute(
        "select name, engine, category from character where id=?", 
        (character_id, )
    ).fetchone()
    engine = get_engine(engine_name)
    effect_list = []

    # have we seen this particular phrase before?
    phrase = cursor.execute("""
        SELECT id FROM phrases WHERE character_id=? AND text=?
    """, (character_id, message)).fetchone()
    if phrase is None:
        # it does not exist, now it does.
        cursor.execute("""
            INSERT INTO phrases (character_id, text) VALUES (?, ?)
        """, (character_id, message))
        con.commit()

    try:
        clean_name = re.sub(r'[^\w]', '', name)
        os.mkdir(os.path.join("clip_library", category, clean_name))
    except OSError as error:
        # the directory already exists.  This is not a problem.
        pass

    sink = Distributor([
        SoundDevice(),
        WaveFile(cachefile + '.wav')
    ])
    
    selected_name = tkvar_ish(f"{category} {name}")

    engine(None, con, selected_name).say(message, effect_list, sink=sink)
    audio = pydub.AudioSegment.from_wav(cachefile + ".wav")
    audio.export(cachefile, format="mp3")
    os.unlink(cachefile + ".wav")
