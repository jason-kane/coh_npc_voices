import tkinter as tk
from tkinter import ttk

from dataclasses import dataclass, field
import tts.sapi
import tempfile
import voicebox
from google.cloud import texttospeech
from voicebox.types import StrOrSSML
from voicebox.audio import Audio
from db import get_cursor, commit
import sys

import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

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


def get_character_by_raw_name(character_name):
    cursor = get_cursor()
    category, name = character_name.split(maxsplit=1)
    return cursor.execute(
        'SELECT id, name, engine, category FROM character WHERE name = ? AND category = ?',
        (name, category)
    ).fetchone()

# Base Class for engines
class TTSEngine(tk.Frame):
    def __init__(self, parent, selected_character, *args, **kwargs):        
        super().__init__(parent, *args, **kwargs)
        self.parent = parent
        self.selected_character = selected_character
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
    
    def load_character(self, raw_name):
        # Retrieve configuration settings from the DB
        # and use them to set values on widgets
        log.info(f'load_character({raw_name})')
        cursor = get_cursor()
        
        character = get_character_by_raw_name(raw_name)
        if character is None:
            log.info('No engine configuration available in the database')
            return
        
        character_id, _, engine, category = character
        for (param_id, key, value) in cursor.execute(
            'SELECT id, key, value FROM base_tts_config WHERE character_id = ?',
            (character_id, )
        ).fetchall():
            if key in self.parameters:
                log.info(f'Assigning value for {key} -> {value}')
                getattr(self, key).set(value)
            else:
                log.info(f'The database has no value for {key}')

    def save_character(self, raw_name):
        # Retrieve configuration settings from widgets
        # and persist them to the DB
        log.info(f'save_character({raw_name})')
        cursor = get_cursor()
        character_id, name, engine, category = get_character_by_raw_name(raw_name)

        for key in self.parameters:
            log.info(f'Processing attribute {key}...')
            # do we already have a value for this key?
            value = str(getattr(self, key).get())
            
            row = cursor.execute(
                'SELECT id, value from base_tts_config WHERE character_id = ? and key = ?',
                (character_id, key)
            ).fetchone()

            if row:
                row_id, old_value = row

                if old_value != value:
                    log.info(f"Updating {key}.  Changing {old_value} to {value}")
                    cursor.execute(
                        'UPDATE base_tts_config SET value = ? WHERE id = ?',
                        (value, row_id)
                    )
                    commit()

            else:
                # we do not have an existing value
                log.info(f'Saving to database: ({character_id!r}, {key!r}, {value!r})')
                cursor.execute('INSERT INTO base_tts_config (character_id, key, value) VALUES (:character_id, :key, :value)', {
                        'character_id': character_id, 
                        'key': key, 
                        'value': value
                    }
                )
                commit()       


class WindowsTTS(TTSEngine):
    cosmetic = "Windows TTS"
    def __init__(self, parent, selected_character, *args, **kwargs):
        super().__init__(parent, selected_character, *args, **kwargs)
        self.selected_character = selected_character
        self.voice_name = tk.StringVar()
        self.rate = tk.IntVar(value=1)

        self.parameters = set((
            'voice_name',
            'rate'
        ))
        self.load_character(self.selected_character.get())
        
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
        
        self.voice_name.trace_add("write", self.change_voice_name)
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
        self.save_character(self.selected_character.get())
    
    def change_voice_name(self, a, b, c):
        # pull the chosen voice name out of variable linked to the widget
        voice_name = self.voice_name.get()
        log.warning(f'saving change of voice_name to {voice_name}')
        self.save_character(self.selected_character.get())

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
    def __init__(self, parent, selected_character, *args, **kwargs):        
        super().__init__(parent, selected_character, *args, **kwargs)

        self.selected_character = selected_character

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

        self.load_character(self.selected_character.get())

        gender = self.get_gender(self.selected_character.get())
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
        voice_frame.pack(side='top', fill='x', expand=True)

        self.voice_name.trace_add("write", self.change_voice_name)

        # when voice_combo changes re-set this
        # gender label.
        tk.Label(
            self,
            textvariable=self.ssml_gender,
            anchor="e"
        ).pack(side="top", fill='x', expand=True)

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
        cursor = get_cursor()
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
        gender = self.get_gender(self.selected_character.get())
        if gender:
            self.ssml_gender.set(gender[0])
        self.save_npc(self.selected_character.get())

    def change_voice_rate(self, a, b, c):
        self.save_npc(self.selected_character.get())

    def change_voice_pitch(self, a, b, c):
        self.save_npc(self.selected_character.get())

    def get_language_codes(self):
        return ['en-US', ]
    
    def get_voice_names(self):
        cursor = get_cursor()
        
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
            commit()
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
    def __init__(self, parent, selected_character, *args, **kwargs):        
        super().__init__(parent, selected_character, *args, **kwargs)


class ElevenLabs(TTSEngine):
    cosmetic = "Eleven Labs"
    def __init__(self, parent, selected_character, *args, **kwargs):        
        super().__init__(parent, selected_character, *args, **kwargs)


def get_engine(engine_name):
    for engine_cls in ENGINE_LIST:
        if engine_name == engine_cls.cosmetic:
            print(f'found {engine_cls.cosmetic}')
            return engine_cls

ENGINE_LIST = [WindowsTTS, GoogleCloud, ]  # AmazonPolly, ElevenLabs]
