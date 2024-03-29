import tkinter as tk
from tkinter import ttk

from dataclasses import dataclass, field
import tts.sapi
import tempfile
import voicebox
from google.cloud import texttospeech
from voicebox.types import StrOrSSML
from voicebox.audio import Audio

import logging
log = logging.getLogger('__name__')


default_engine = 'Windows TTS'

@dataclass
class WindowsSapi(voicebox.tts.tts.TTS):

    rate: int = 1

    def get_speech(self, text: StrOrSSML) -> Audio:
        voice = tts.sapi.Sapi()
        voice.set_rate(self.rate)

        with tempfile.NamedTemporaryFile() as tmp:
            # just need the safe filename
            tmp.close()
            voice.create_recording(tmp.name, text)
            audio = voicebox.tts.utils.get_audio_from_wav_file(tmp.name)
        return audio


def get_npc_by_name(cursor, npc_name):
    return cursor.execute(
        'SELECT * FROM npc WHERE name = ?',
        (npc_name, )
    ).fetchone()

# Base Class for engines
class TTSEngine(tk.Frame):
    def __init__(self, parent, con, selected_npc, *args, **kwargs):        
        super().__init__(parent, *args, **kwargs)
        self.parent = parent
        self.con = con
        self.selected_npc = selected_npc
        self.parameters = set()

    def say(self, message, effects, sink=None, *args, **kwargs):
        vb = voicebox.SimpleVoicebox(
            tts=self.get_tts(),
            effects=effects,
            sink=sink
        )
        vb.say(message)

    def get_tts(self):
        return voicebox.tts.tts.TTS()
    
    def load_npc(self, npc_name):
        # Retrieve configuration settings from the DB
        # and use them to set values on widgets
        cursor = self.con.cursor()
        
        npc = get_npc_by_name(cursor, npc_name)
        if npc is None:
            log.info('No engine configuration available in the database')
            return
        
        npc_id, _, engine = npc
        for (param_id, key, value) in cursor.execute(
            'SELECT id, key, value FROM base_tts_config WHERE npc_id = ?',
            (npc_id, )
        ).fetchall():
            if key in self.parameters:
                getattr(self, key).set(value)

    def save_npc(self, npc_name):
        # Retrieve configuration settings from widgets
        # and persist them to the DB
        cursor = self.con.cursor()
        npc_id, _, engine = get_npc_by_name(cursor, npc_name)

        for key in self.parameters:
            # do we already have a value for this key?
            value = str(getattr(self, key).get())
            
            row = cursor.execute(
                'SELECT id, value from base_tts_config WHERE npc_id = ? and key = ?',
                (npc_id, key)
            ).fetchone()

            if row:
                row_id, old_value = row

                if old_value != value:
                    log.debug(f"Updating {key}.  Changing {old_value} to {value}")
                    cursor.execute(
                        'UPDATE base_tts_config SET value = ? WHERE id = ?',
                        (value, row_id)
                    )
                    self.con.commit()

            else:
                # we do not have an existing value
                log.debug(f'Saving to database: ({npc_id!r}, {key!r}, {value!r})')
                cursor.execute('INSERT INTO base_tts_config (npc_id, key, value) VALUES (:npc_id, :key, :value)', {
                        'npc_id': npc_id, 
                        'key': key, 
                        'value': value
                    }
                )
                self.con.commit()       


class WindowsTTS(TTSEngine):
    cosmetic = "Windows TTS"
    def __init__(self, parent, con, selected_npc, *args, **kwargs):
        super().__init__(parent, con, selected_npc, *args, **kwargs)

        self.voice_name = tk.StringVar()
        self.rate = tk.IntVar(value=1)

        self.parameters = set((
            'voice_name',
            'rate'
        ))
        self.load_npc(self.selected_npc.get())
        
        voice_frame = tk.Frame(self)
        tk.Label(
            voice_frame,
            text='Voice Name',
            anchor="e"
        ).pack(side='left', fill='x', expand=True)

        voice_combo = ttk.Combobox(
            voice_frame, 
            textvariable=self.voice_name, 
        )
        all_voices = self.get_voice_names()
        voice_combo['values'] = all_voices
        voice_combo['state'] = 'readonly'
        voice_combo.pack(side='left', fill='x', expand=True)

        self.voice_name.set(all_voices[0])
        voice_frame.pack(side='top', fill='x', expand=True)

        rate_frame = tk.Frame(self)
        tk.Label(
            rate_frame,
            text='Speaking Rate',
            anchor="e"
        ).pack(side='left', fill='x', expand=True)

        # Set the speed of the speaker -10 is slowest, 10 is fastest
        tk.Scale(
            rate_frame, 
            from_=-10,
            to=10,
            orient='horizontal',
            variable=self.rate,
            resolution=1
        ).pack(side='left', fill='x', expand=True)
        self.rate.trace_add("write", self.change_voice_rate)
        rate_frame.pack(side='top', fill='x', expand=True)

    def change_voice_rate(self, a, b, c):
        self.save_npc(self.selected_npc.get())

    def get_tts(self):
        return WindowsSapi(
            rate=self.rate.get()
        )
    
    def get_voice_names(self):
        """
        return a sorted list of available voices
        I don't know how much this list will vary
        from windows version to version and from
        machine to machine.
        """
        voice = tts.sapi.Sapi()
        return sorted(voice.get_voice_names())


class GoogleCloud(TTSEngine):
    cosmetic = "Google Text-to-Speech"
    def __init__(self, parent, con, selected_npc, *args, **kwargs):        
        super().__init__(parent, con, selected_npc, *args, **kwargs)

        self.con = con
        self.selected_npc = selected_npc

        # with defaults
        self.language_code = tk.StringVar(value='en-US')
        self.voice_name = tk.StringVar(value='en-US-Casual-K')
        self.ssml_gender = tk.StringVar(value='MALE')
        self.rate = tk.DoubleVar(value=1.0)
        self.pitch = tk.DoubleVar(value=0.0)

        self.parameters = set((
            'language_code',
            'voice_name',
            'rate',
            'pitch'
        ))

        self.load_npc(self.selected_npc.get())

        gender = self.get_gender(self.selected_npc.get())
        if gender:
            self.ssml_gender.set(gender[0])
        else:
            log.warning('Voice has no associated gender (even neutral)')

        language_frame = tk.Frame(self)
        tk.Label(
            language_frame,
            text='Language Code',
            anchor="e"
        ).pack(side='left', fill='x', expand=True)

        language_combo = ttk.Combobox(
            language_frame, 
            textvariable=self.language_code, 
        )
        all_languages = self.get_language_codes()
        self.language_code.set(all_languages[0])
        language_combo['values'] = all_languages
        language_combo['state'] = 'readonly'

        language_combo.pack(side='left')
        language_frame.pack(side='top', fill='x', expand=True)

        voice_frame = tk.Frame(self)
        tk.Label(
            voice_frame,
            text='Voice Name',
            anchor="e"
        ).pack(side='left', fill='x', expand=True)

        voice_combo = ttk.Combobox(
            voice_frame, 
            textvariable=self.voice_name, 
        )
        all_voices = self.get_voice_names()
        voice_combo['values'] = all_voices
        voice_combo['state'] = 'readonly'
        voice_combo.pack(side='left', fill='x', expand=True)

        self.voice_name.set(all_voices[0])
        voice_frame.pack(side='top', fill='x', expand=True)

        # when voice_combo changes re-set this
        # gender label.
        tk.Label(
            self,
            textvariable=self.ssml_gender,
            anchor="e"
        ).pack(side="top", fill='x', expand=True)
        self.voice_name.trace_add("write", self.change_voice_name)

        rate_frame = tk.Frame(self)
        tk.Label(
            rate_frame,
            text='Speaking Rate',
            anchor="e"
        ).pack(side='left', fill='x', expand=True)

        # Optional. Input only. Speaking rate/speed, in the range [0.25, 4.0]. 
        # 1.0 is the normal native speed supported by the specific voice. 2.0 
        # is twice as fast, and 0.5 is half as fast. If unset(0.0), defaults 
        # to the native 1.0 speed. Any other values < 0.25="" or=""> 4.0 will 
        # return an error.
        tk.Scale(
            rate_frame, 
            from_=0.25,
            to=4.0,
            orient='horizontal',
            variable=self.rate,
            resolution=0.25
        ).pack(side='left', fill='x', expand=True)
        self.rate.trace_add("write", self.change_voice_rate)
        rate_frame.pack(side='top', fill='x', expand=True)

        pitch_frame = tk.Frame(self)
        tk.Label(
            pitch_frame,
            text='Vocal Pitch',
            anchor="e"
        ).pack(side='left', fill='x', expand=True)

        # Optional. Input only. Speaking pitch, in the range [-20.0, 20.0]. 
        # 20 means increase 20 semitones from the original pitch. -20 means 
        # decrease 20 semitones from the original pitch.
        tk.Scale(
            pitch_frame, 
            from_=-20.0,
            to=20.0,
            orient='horizontal',
            variable=self.pitch,
            resolution=0.25
        ).pack(side='left', fill='x', expand=True)
        self.pitch.trace_add("write", self.change_voice_pitch)
        pitch_frame.pack(side='top', fill='x', expand=True)

    def get_gender(self, voice_name):
        cursor = self.con.cursor()
        gender = cursor.execute("""
            SELECT
                ssml_gender
            FROM
                google_voices
            WHERE
                name=?  
        """, (self.voice_name.get(), )).fetchone()
        return gender

    def change_voice_name(self, a, b, c):
        # the user have chosen a different voice name
        gender = self.get_gender(self.selected_npc.get())
        if gender:
            self.ssml_gender.set(gender[0])
        self.save_npc(self.selected_npc.get())

    def change_voice_rate(self, a, b, c):
        self.save_npc(self.selected_npc.get())

    def change_voice_pitch(self, a, b, c):
        self.save_npc(self.selected_npc.get())

    def get_language_codes(self):
        return ['en-US', ]
    
    def get_voice_names(self):
        cursor = self.con.cursor()
        
        all_voices = cursor.execute(
            'SELECT name FROM google_voices WHERE language_code = ? ORDER BY name',
            (self.language_code.get(), )
        ).fetchall()

        if all_voices:
            return [voice[0] for voice in all_voices]
        else:
            # we don't have voices in the DB
            client = texttospeech.TextToSpeechClient()
            req = texttospeech.ListVoicesRequest(language_code=self.language_code.get())
            resp = client.list_voices(req)
            for voice in resp.voices:
                cursor.execute("""
                    INSERT into google_voices (name, language_code, ssml_gender) VALUES (:name, :language_code, :ssml_gender)
                """, {
                    'name': voice.name,
                    'language_code': self.language_code.get(),
                    'ssml_gender': texttospeech.SsmlVoiceGender(voice.ssml_gender).name
                })
            self.con.commit()
            return sorted([n.name for n in resp.voices])
        
    def get_tts(self):
        # self.rate?
        # self.pitch?
        client = texttospeech.TextToSpeechClient()
        kwargs = {
            'language_code': self.language_code.get(),
            'name': self.voice_name.get(),
            'ssml_gender': self.ssml_gender.get()
        }

        audio_config = texttospeech.AudioConfig(
            speaking_rate=float(self.rate.get()),
            pitch=float(self.pitch.get())
        )

        log.debug('texttospeech.VoiceSelectionParams(%s)' % kwargs)
        voice_params = texttospeech.VoiceSelectionParams(
            **kwargs
            # texttospeech.SsmlVoiceGender.NEUTRAL
        )
        return voicebox.tts.GoogleCloudTTS(
            client=client,
            voice_params=voice_params,
            audio_config=audio_config
        )


class AmazonPolly(TTSEngine):
    cosmetic = "Amazon Polly"
    def __init__(self, parent, con, selected_npc, *args, **kwargs):        
        super().__init__(parent, con, selected_npc, *args, **kwargs)


class ElevenLabs(TTSEngine):
    cosmetic = "Eleven Labs"
    def __init__(self, parent, con, selected_npc, *args, **kwargs):        
        super().__init__(parent, con, selected_npc, *args, **kwargs)


def get_engine(engine_name):
    for engine_cls in ENGINE_LIST:
        if engine_name == engine_cls.cosmetic:
            print(f'found {engine_cls.cosmetic}')
            return engine_cls

ENGINE_LIST = [WindowsTTS, GoogleCloud, ]  # AmazonPolly, ElevenLabs]
