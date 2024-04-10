import logging
import sys
import tempfile
import time
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from sqlalchemy import select, update
import db
import models
import tts.sapi
import voicebox
from google.cloud import texttospeech
from voicebox.audio import Audio
from voicebox.types import StrOrSSML

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
            # this can:
            #   File "C:\Users\jason\Desktop\coh_npc_voices\venv\Lib\site-packages\tts\sapi.py", line 93, in say
            #     self.voice.Speak(message, flag)
            # _ctypes.COMError: (-2147200958, None, ('XML parser error', None, None, 0, None))

            success = False
            while not success:
                try:
                    voice.create_recording(tmp.name, text)
                    success = True
                except Exception as err:
                    log.error(err)
                    log.error('Text was: %s', text)
                    time.sleep(0.1)

            audio = voicebox.tts.utils.get_audio_from_wav_file(tmp.name)
        return audio


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
        log.info(f'TTSEngine.load_character({raw_name})')
        category, name = raw_name.split(maxsplit=1)

        with models.Session(models.engine) as session:
            character = session.scalars(
                select(models.Character).where(
                    models.Character.name==name,
                    models.Character.category==models.category_str2int(category)
                )
            ).first()

        if character is None:
            log.info('No engine configuration available in the database')
            return
        
        with models.Session(models.engine) as session:
            tts_config = session.scalars(
                select(models.BaseTTSConfig).where(
                    models.BaseTTSConfig.character_id==character.id
                )
            ).all()

            for config in tts_config:
                if config.key in self.parameters:
                    getattr(self, config.key).set(config.value)
                    setattr(self, config.key + "_base", config.value)
        
        return character
                
    def save_character(self, raw_name):
        # Retrieve configuration settings from widgets
        # and persist them to the DB
        log.info(f'save_character({raw_name})')

        with models.Session(models.engine) as session:
            category, name = raw_name.split(maxsplit=1)
            character = session.scalars(
                select(models.Character).where(
                    models.Character.name==name,
                    models.Character.category==models.category_str2int(category)
                )
            ).first()

            if character is None:
                # new character?  This is not typical.
                character = models.Character(
                    name=name,
                    category=models.category_str2int(category),
                    engine=default_engine
                )
                session.add(character)
                session.commit()
                log.info('character: %s', character)
                session.refresh(character)

            for key in self.parameters:
                log.debug(f'Processing attribute {key}...')
                # do we already have a value for this key?
                value = str(getattr(self, key).get())

                # do we already have a value for this key?
                config_setting = session.execute(
                    select(models.BaseTTSConfig).where(
                        models.BaseTTSConfig.character_id==character.id,
                        models.BaseTTSConfig.key==key
                    )
                ).scalar_one_or_none()

                if config_setting and config_setting.value != value:
                    # update an existing setting
                    config_setting.value = value
                    session.commit()
                elif not config_setting:
                    # save a new setting
                    new_config_setting = models.BaseTTSConfig(
                        character_id=character.id,
                        key=key,
                        value=value
                    )
                    session.add(new_config_setting)

            session.commit()


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
        rate = self.rate.get()
        if getattr(self, "rate_base", -20) != rate:
            self.save_character(self.selected_character.get())
    
    def change_voice_name(self, a, b, c):
        # pull the chosen voice name out of variable linked to the widget
        voice_name = self.voice_name.get()
        
        if getattr(self, "voice_name_base", "") != voice_name:
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

    def change_voice_name(self, a, b, c):
        # the user have chosen a different voice name
        # find the voice they chose
        with models.Session(models.engine) as session:
            self.voice = session.execute(
                select(models.GoogleVoices).where(
                    models.GoogleVoices.name==self.voice_name.get()
                )
            ).scalar_one_or_none()
            self.ssml_gender.set(self.voice.ssml_gender)

        self.save_character(self.selected_character.get())

    def change_voice_rate(self, a, b, c):
        self.save_character(self.selected_character.get())

    def change_voice_pitch(self, a, b, c):
        self.save_character(self.selected_character.get())

    def get_language_codes(self):
        return ['en-US', ]
    
    def get_voice_names(self):
        with models.Session(models.engine) as session:
            all_voices = session.execute(
                select(models.GoogleVoices).where(
                    models.GoogleVoices.language_code==self.language_code.get()
                ).order_by(models.GoogleVoices.name)
            ).scalars()
        
            if all_voices:
                return [voice.name for voice in all_voices]
            else:
                # we don't have voices in the DB
                client = texttospeech.TextToSpeechClient()
                req = texttospeech.ListVoicesRequest(language_code=self.language_code.get())
                resp = client.list_voices(req)
                
                for voice in resp.voices:
                    new_voice = models.GoogleVoices(
                        name=voice.name,
                        language_code=self.language_code.get(),
                        ssml_gender=texttospeech.SsmlVoiceGender(voice.ssml_gender).name
                    )
                    session.add(new_voice)
                session.commit()

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
