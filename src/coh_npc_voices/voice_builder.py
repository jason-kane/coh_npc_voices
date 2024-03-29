from voicebox.sinks import Distributor, SoundDevice, WaveFile
import pydub
import os
import re
from engines import get_engine

default_engine = "Windows TTS"

class tkvar_ish:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value

def create(con, npc_id, message, cachefile):
    """
    This NPC exists in our database but we don't
    have this particular message rendered.

    1. Get vocal characteristics from sqlite using 
       the npc_id
    2. Render message based on that data
    3. persist as an mp3 in cachefile
    """
    cursor = con.cursor()
    name, engine_name = cursor.execute(
        "select name, engine from npc where id=?", 
        (npc_id, )
    ).fetchone()
    engine = get_engine(engine_name)
    effect_list = []

    # have we seen this particular phrase before?
    phrase = cursor.execute("""
        SELECT id FROM phrases WHERE npc_id=? AND text=?
    """, (npc_id, message)).fetchone()
    if phrase is None:
        # it does not exist, now it does.
        cursor.execute("""
            INSERT INTO phrases (npc_id, text) VALUES (?, ?)
        """, (npc_id, message))
        con.commit()

    try:
        clean_name = re.sub(r'[^\w]', '', name)
        os.mkdir(os.path.join("clip_library", clean_name))
    except OSError as error:
        # the directory already exists.  This is not a problem.
        pass

    sink = Distributor([
        SoundDevice(),
        WaveFile(cachefile + '.wav')
    ])
    
    selected_name = tkvar_ish(name)

    engine(None, con, selected_name).say(message, effect_list, sink=sink)
    audio = pydub.AudioSegment.from_wav(cachefile + ".wav")
    audio.export(cachefile, format="mp3")
    os.unlink(cachefile + ".wav")
