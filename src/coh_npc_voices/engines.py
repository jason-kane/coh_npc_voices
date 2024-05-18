import json
import logging
import os
import random
import sys
import tempfile
import time
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Union
import boto3

from voicebox.tts.amazonpolly import AmazonPolly as AmazonPollyTTS

import audio
import elevenlabs
import models
import settings
import tts.sapi
import voicebox
from elevenlabs.client import ElevenLabs as ELABS
from google.cloud import texttospeech
from sqlalchemy import select
from voicebox.audio import Audio
from voicebox.types import StrOrSSML

logging.basicConfig(
    level=settings.LOGLEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("__name__")


class DISABLE_ENGINES(Exception):
    """
    signal to disable this engine for this session
    """

@dataclass
class WindowsSapi(voicebox.tts.tts.TTS):
    rate: int = 1
    voice: str = "Zira"

    def get_speech(self, text: StrOrSSML) -> Audio:
        voice = tts.sapi.Sapi()
        log.info(f"Saying {text!r} as {self.voice} at rate {self.rate}")
        voice.set_rate(self.rate)
        voice.set_voice(self.voice)

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
                    # create a temporary wave file
                    voice.create_recording(tmp.name, text)
                    success = True
                except Exception as err:
                    log.error(err)
                    log.error("Text was: %s", text)
                    time.sleep(0.1)

            audio = voicebox.tts.utils.get_audio_from_wav_file(tmp.name)
        return audio


# Base Class for engines
class TTSEngine(ttk.Frame):
    def __init__(self, parent, rank, selected_character, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.rank = rank
        self.parent = parent
        self.selected_character = selected_character
        self.override = {}
        self.parameters = set('voice_name')

    def say(self, message, effects, sink=None, *args, **kwargs):
        tts = self.get_tts()
        log.info(f'{self}.say({message=}, {effects=}, {sink=}, {args=}, {kwargs=}')
        log.info(f'Invoking voicebox.SimpleVoicebox({tts=}, {effects=}, {sink=})')
        vb = voicebox.SimpleVoicebox(
            tts=tts,
            effects=effects, 
            sink=sink
        )

        if message:
            log.info(f"say.message: {message}")
            try:
                vb.say(message)
            except Exception as err:
                log.error('vb: %s', vb)
                log.error("Error in TTSEngine.say(): %s", err)
                if err.status_code == 401:
                    log.error(err.body)
                    if err.body.get('detail', {}).get('status') == "quota_exceeded":
                        raise DISABLE_ENGINES
                raise

    def get_tts(self):
        return voicebox.tts.tts.TTS()

    def load_character(self, raw_name):
        # Retrieve configuration settings from the DB
        # and use them to set values on widgets
        self.loading = True
        log.info(f"TTSEngine.load_character({raw_name})")
       
        character = models.get_character_from_rawname(raw_name)
        self.gender = settings.get_npc_gender(character.name)

        # if character.engine == self.cosmetic:
        #     self.rank = "primary"
        # elif character.engine_secondary == self.cosmetic:
        #     self.rank = "secondary"

        log.info(f'Engine {character.engine} found.')
        with models.Session(models.engine) as session:
            tts_config = session.scalars(
                select(models.BaseTTSConfig).where(
                    models.BaseTTSConfig.character_id == character.id,
                    models.BaseTTSConfig.rank == self.rank
                )
            ).all()
            log.info(f"{tts_config=}")

            for config in tts_config:
                log.info(f'Setting config {config.key} to {config.value}')
                log.info(f'{self} supports parameters {self.parameters}')
                if config.key in self.parameters:
                    # log.info(f"{dir(self)}")
                    if hasattr(self, 'config_vars'):
                        # the polly way
                        log.info(f'PolyConfig[{config.key}] = {config.value}')
                        self.config_vars[config.key].set(config.value)
                    else:
                        log.info(f'oldstyle config[{config.key}] = {config.value}')
                        # everything else
                        getattr(self, config.key).set(config.value)
                        setattr(self, config.key + "_base", config.value)
        # else:
        #     # Unusual situation.  We are trying to use the "wrong" tts engine
        #     # for this character. That means we also have the wrong
        #     # BaseTTSConfig and .. we don't want to mess with the existing
        #     # configuration.  Oh, and it should still mostly work and be
        #     # consistent. Use case for this nonesense?
        #     #
        #     # You're rolling with Elevenlabs and you run out of free voice
        #     # credits.  We want to smoothly transition to Google voices.  When
        #     # Elevenlabs starts working again, we don't want the voice configs
        #     # to be messed up.
        #     #
        #     # we keep effects, that part is easy.           
        #     self.gender = settings.get_npc_gender(character.name)
            
        #     # we can't do simple random, we want a _consistent_ voice.  No
        #     # problem. gendered_voices should be identical from one "run" to the
        #     # next.
        #     gendered_voices = sorted(self.get_voice_names(gender=self.gender))
            
        #     # when is random not random?  We don't even need to hash it,
        #     # random.seed now takes an int (obv) _or_ a str/bytes/bytearray.  
        #     random.seed(a=character.name, version=2)
            
        #     # easy as that.  gendered voice name chosen with a good spread of
        #     # all available voice names, and the same character speaking twice
        #     # gets the same voice.  Even across sessions.  Even across upgrades.
        #     voice_name = random.choice(gendered_voices)

        #     # if we self.voice_name.set(voice_name) the way that feels natural
        #     # we're going to reconfigure the character in exactly the way we
        #     # don't want. Jumbo-dict of reasonable choices for all engines. this
        #     # is clearly unsustainable.  I'm thinking each character and preset
        #     # gets a full primary and secondary voice config.
        #     self.override['voice_name'] = voice_name
        #     self.override['rate'] = 1
        #     self.override['stabiity'] = 0.71
        #     self.override['similarity_boost'] = 0.5
        #     self.override['style'] = 0.0
        #     self.override['use_speaker_boost'] = True

        log.info("TTSEngine.load_character complete")
        self.loading = False
        return character

    def save_character(self, raw_name):
        # Retrieve configuration settings from widgets
        # and persist them to the DB
        log.info(f"save_character({raw_name})")

        with models.Session(models.engine) as session:
            category, name = raw_name.split(maxsplit=1)
            character = models.get_character(name, category)

            if character is None:
                # new character?  This is not typical.
                log.info(f'Creating new character {name}`')
                character = models.Character(
                    name=name,
                    category=models.category_str2int(category),
                    engine=settings.get_config_key(
                        'DEFAULT_ENGINE', settings.DEFAULT_ENGINE
                    ),
                )
                session.add(character)
                session.commit()
                session.refresh(character)

            log.info("character: %s", character)
            for key in self.parameters:
                log.info(f"Processing attribute {key}...")
                # do we already have a value for this key?
                value = str(getattr(self, key).get())

                # do we already have a value for this key?
                config_setting = session.execute(
                    select(models.BaseTTSConfig).where(
                        models.BaseTTSConfig.character_id == character.id,
                        models.BaseTTSConfig.rank == self.rank,
                        models.BaseTTSConfig.key == key,
                    )
                ).scalar_one_or_none()

                if config_setting and config_setting.value != value:
                    log.info('Updating existing setting')
                    config_setting.value = value
                    session.commit()

                elif not config_setting:
                    log.info('Saving new BaseTTSConfig')
                    new_config_setting = models.BaseTTSConfig(
                        character_id=character.id, 
                        rank=self.rank,
                        key=key, 
                        value=value
                    )
                    session.add(new_config_setting)

            session.commit()


class WindowsTTS(TTSEngine):
    cosmetic = "Windows TTS"

    def __init__(self, parent, rank, selected_character, *args, **kwargs):
        super().__init__(parent, selected_character, *args, **kwargs)
        self.rank = rank
        self.selected_character = selected_character
        self.voice_name = tk.StringVar()
        self.rate = tk.IntVar(value=1)

        self.parameters = set(("voice_name", "rate"))
        self.load_character(self.selected_character.get())

        voice_frame = ttk.Frame(self)
        ttk.Label(voice_frame, text="Voice Name", anchor="e").pack(
            side="left", fill="x", expand=True
        )

        voice_combo = ttk.Combobox(
            voice_frame,
            textvariable=self.voice_name,
        )
        all_voices = self.get_voice_names()
        voice_combo["values"] = all_voices
        voice_combo["state"] = "readonly"
        voice_combo.pack(side="left", fill="x", expand=True)

        self.voice_name.trace_add("write", self.change_voice_name)
        voice_frame.pack(side="top", fill="x", expand=True)

        rate_frame = ttk.Frame(self)
        ttk.Label(rate_frame, text="Speaking Rate", anchor="e").pack(
            side="left", fill="x", expand=True
        )

        # Set the speed of the speaker -10 is slowest, 10 is fastest
        tk.Scale(
            rate_frame,
            from_=-10,
            to=10,
            orient="horizontal",
            variable=self.rate,
            resolution=1,
        ).pack(side="left", fill="x", expand=True)
        self.rate.trace_add("write", self.change_voice_rate)
        rate_frame.pack(side="top", fill="x", expand=True)

    def change_voice_rate(self, a, b, c):
        rate = self.rate.get()
        if getattr(self, "rate_base", -20) != rate:
            self.save_character(self.selected_character.get())

    def change_voice_name(self, a, b, c):
        # pull the chosen voice name out of variable linked to the widget
        voice_name = self.voice_name.get()

        if getattr(self, "voice_name", "") != voice_name:
            log.warning(f"saving change of voice_name to {voice_name}")
            self.save_character(self.selected_character.get())

    def get_tts(self):
        # So.  What happens when the chosen voice isn't actually
        # installed?
        rate = self.override.get('rate', self.rate.get())
        voice_name = self.override.get('voice_name', self.voice_name.get())
        return WindowsSapi(rate=rate, voice=voice_name)

    @staticmethod
    def get_voice_names(language_code=None, gender=None):
        """
        return a sorted list of available voices
        I don't know how much this list will vary
        from windows version to version and from
        machine to machine.
        """
        voice = tts.sapi.Sapi()
        nice_names = []
        for voice in voice.get_voice_names():
            name = " ".join(voice.split("-")[0].split()[1:])

            if gender == "female":
                # filter to only include female voices.  No doubt
                # these lists are ridiculously incomplete.
                if name not in [
                    "Catherine",
                    "Hazel",
                    "Hazel Desktop",
                    "Heera",
                    "Linda",
                    "Susan",
                    "Zira",
                    "Zira Desktop",
                ]:
                    continue
            elif gender == "male":
                if name not in [
                    "David",
                    "David Desktop",
                    "George",
                    "James",
                    "Mark",
                    "Ravi",
                    "Richard",
                    "Sean",
                ]:
                    continue

            nice_names.append(name)

        return sorted(nice_names)


class GoogleCloud(TTSEngine):
    cosmetic = "Google Text-to-Speech"

    def __init__(self, parent, rank, selected_character, *args, **kwargs):
        super().__init__(parent, rank, selected_character, *args, **kwargs)
        self.rank = rank
        self.selected_character = selected_character

        # with defaults
        self.language_code = tk.StringVar(value="en-US")
        self.voice_name = tk.StringVar(value="")
        # ssml_gender handling is sloppy
        self.ssml_gender = tk.StringVar(value="MALE")
        self.rate = tk.DoubleVar(value=1.0)
        self.pitch = tk.DoubleVar(value=0.0)

        self.parameters = set(("language_code", "voice_name", "rate", "pitch"))

        character = self.load_character(self.selected_character.get())
        gender = settings.get_npc_gender(character.name)

        language_frame = ttk.Frame(self)
        ttk.Label(language_frame, text="Language Code", anchor="e").pack(
            side="left", fill="x", expand=True
        )

        language_combo = ttk.Combobox(
            language_frame,
            textvariable=self.language_code,
        )
        all_languages = self.get_language_codes()
        language_combo["values"] = all_languages
        language_combo["state"] = "readonly"

        language_combo.pack(side="left")
        language_frame.pack(side="top", fill="x", expand=True)

        voice_frame = ttk.Frame(self)
        ttk.Label(voice_frame, text="Voice Name", anchor="e").pack(
            side="left", fill="x", expand=True
        )

        voice_combo = ttk.Combobox(
            voice_frame,
            textvariable=self.voice_name,
        )
        all_voices = self.get_voice_names(
            language_code=self.language_code.get(),
            gender=gender
        )
        voice_combo["values"] = all_voices
        voice_combo["state"] = "readonly"
        voice_combo.pack(side="left", fill="x", expand=True)
        voice_frame.pack(side="top", fill="x", expand=True)
        self.voice_name.set(value=all_voices[0])

        self.voice_name.trace_add("write", self.change_voice_name)

        # when voice_combo changes re-set this
        # gender label.
        ttk.Label(self, textvariable=self.ssml_gender, anchor="e").pack(
            side="top", fill="x", expand=True
        )

        rate_frame = ttk.Frame(self)
        ttk.Label(rate_frame, text="Speaking Rate", anchor="e").pack(
            side="left", fill="x", expand=True
        )

        # Optional. Input only. Speaking rate/speed, in the range [0.25, 4.0].
        # 1.0 is the normal native speed supported by the specific voice. 2.0
        # is twice as fast, and 0.5 is half as fast. If unset(0.0), defaults
        # to the native 1.0 speed. Any other values < 0.25="" or=""> 4.0 will
        # return an error.
        tk.Scale(
            rate_frame,
            from_=0.25,
            to=4.0,
            orient="horizontal",
            variable=self.rate,
            resolution=0.25,
        ).pack(side="left", fill="x", expand=True)
        self.rate.trace_add("write", self.change_voice_rate)
        rate_frame.pack(side="top", fill="x", expand=True)

        pitch_frame = ttk.Frame(self)
        ttk.Label(pitch_frame, text="Vocal Pitch", anchor="e").pack(
            side="left", fill="x", expand=True
        )

        # Optional. Input only. Speaking pitch, in the range [-20.0, 20.0].
        # 20 means increase 20 semitones from the original pitch. -20 means
        # decrease 20 semitones from the original pitch.
        tk.Scale(
            pitch_frame,
            from_=-20.0,
            to=20.0,
            orient="horizontal",
            variable=self.pitch,
            resolution=0.25,
        ).pack(side="left", fill="x", expand=True)
        self.pitch.trace_add("write", self.change_voice_pitch)
        pitch_frame.pack(side="top", fill="x", expand=True)

    def change_voice_name(self, a, b, c):
        # the user have chosen a different voice name
        # find the voice they chose
        with models.Session(models.engine) as session:
            self.voice = session.execute(
                select(models.GoogleVoices).where(
                    models.GoogleVoices.name == self.voice_name.get()
                )
            ).scalar_one_or_none()
            self.ssml_gender.set(self.voice.ssml_gender)

        self.save_character(self.selected_character.get())

    def change_voice_rate(self, a, b, c):
        self.save_character(self.selected_character.get())

    def change_voice_pitch(self, a, b, c):
        self.save_character(self.selected_character.get())

    @staticmethod
    def get_language_codes():
        return [
            "en-US",
        ]

    @staticmethod
    def get_voice_names(language_code="en-US", gender=None):
        if language_code is None:
            language_code = settings.get_config_key('default_google_language_code', 'en-US')

        log.info(f'get_voice_names({language_code=}, {gender=})')
        with models.Session(models.engine) as session:
            all_voices = list(
                session.execute(
                    select(models.GoogleVoices)
                    .where(models.GoogleVoices.language_code == language_code)
                    .order_by(models.GoogleVoices.name)
                ).scalars()
            )

        if all_voices:
            log.info(f"{len(all_voices)} voices found in database")
            if gender:
                out = []
                for result in all_voices:
                    if result.ssml_gender.upper() == gender.upper():
                        out.append(result.name)
                    else:
                        log.info(f'{gender} != {result.ssml_gender}')
                return out
            
                return [
                    voice.name
                    for voice in all_voices
                    if voice.ssml_gender == gender
                ]
            else:
                return [voice.name for voice in all_voices]
        else:
            log.info("Voices are not in the database")
            client = texttospeech.TextToSpeechClient()
            req = texttospeech.ListVoicesRequest(language_code=language_code)
            resp = client.list_voices(req)

            with models.Session(models.engine) as session:
                for voice in resp.voices:
                    new_voice = models.GoogleVoices(
                        name=voice.name,
                        language_code=language_code,
                        ssml_gender=texttospeech.SsmlVoiceGender(
                            voice.ssml_gender
                        ).name,
                    )
                    session.add(new_voice)
                session.commit()

            return sorted([n.name for n in resp.voices])

    @staticmethod
    def get_voice_gender(voice_name):
        with models.Session(models.engine) as session:
            ssml_gender = session.scalars(
                select(models.GoogleVoices.ssml_gender).where(
                    models.GoogleVoices.name == voice_name
                )
            ).first()
        return ssml_gender

    def get_tts(self):
        language_code = self.override.get('language_code', self.language_code.get())
        voice_name = self.override.get('voice_name', self.voice_name.get())

        client = texttospeech.TextToSpeechClient()
        kwargs = {
            "language_code": language_code,
            "name": voice_name,
            # "ssml_gender": self.ssml_gender.get(),
        }

        audio_config = texttospeech.AudioConfig(
            speaking_rate=float(self.rate.get()), pitch=float(self.pitch.get())
        )

        log.info("texttospeech.VoiceSelectionParams(%s)" % kwargs)
        voice_params = texttospeech.VoiceSelectionParams(
            **kwargs
            # texttospeech.SsmlVoiceGender.NEUTRAL
        )
        return voicebox.tts.GoogleCloudTTS(
            client=client, voice_params=voice_params, audio_config=audio_config
        )


def get_elevenlabs_client():
    if os.path.exists("./eleven_labs.key"):
        with open("./eleven_labs.key") as h:
            # umm, I can't do that, can I?
            elvenlabs_api_key = h.read().strip()

        # https://github.com/elevenlabs/elevenlabs-python/blob/main/src/elevenlabs/client.py#L42
        client = ELABS(api_key=elvenlabs_api_key)
        return client
    else:
        log.info("Elevenlabs Requires valid eleven_labs.key file")


def as_gender(in_gender):
    if in_gender in ["female"]:
        return "female"
    if in_gender in ["male"]:
        return "male"
    else:
        return "neutral"

    return in_gender


class ElevenLabs(TTSEngine):
    cosmetic = "Eleven Labs"
    api_key = None
    language_code = ""
    
    def __init__(self, parent, selected_character, *args, **kwargs):
        super().__init__(parent, selected_character, *args, **kwargs)

        self.parameters = ("voice_name", "stability", "similarity_boost", "style", "use_speaker_boost")

        self.CONFIG_TUPLE = (
            ('Voice Name', 'voice_name', tk.StringVar, "<unconfigured>", {}, self.get_voice_names),
            ('Stability', 'stability', tk.DoubleVar, 0.5, {'min': 0, 'max': 1, 'resolution': 0.025}, None),
            ('Similarity Boost', 'similarity_boost', tk.DoubleVar, 0, {'min': 0, 'max': 1, 'resolution': 0.025}, None),
            ('Style', 'style', tk.DoubleVar, 0.0, {'min': 0, 'max': 1, 'resolution': 0.025}, None),
            ('Speaker Boost', 'use_speaker_boost', tk.BooleanVar, True, {}, None)
        )

        self.config_vars = {}
        self.widget = {}

        for cosmetic, key, varfunc, default, cfg, fn in self.CONFIG_TUPLE:
            frame = ttk.Frame(self)
            ttk.Label(frame, text=cosmetic, anchor="e").pack(
                side="left", fill="x", expand=True
            )
            self.config_vars[key] = varfunc(value=default)
            
            if varfunc == tk.StringVar:
                # combo widget for strings
                self.widget[key] = ttk.Combobox(
                    frame,
                    textvariable=self.config_vars[key],
                )
                self.widget[key]["state"] = "readonly"
                self.widget[key].pack(side="left", fill="x", expand=True)
            elif varfunc == tk.DoubleVar:
                # doubles get a scale widget
                self.widget[key] = tk.Scale(
                    frame,
                    variable=self.config_vars[key],
                    from_=cfg.get('min', 0),
                    to=cfg['max'],
                    orient='horizontal',
                    resolution=cfg.get('resolution', 1)
                )
                self.widget[key].pack(side="left", fill="x", expand=True)
            elif varfunc == tk.BooleanVar:
                self.widget[key] = ttk.Checkbutton(
                    frame,
                    text="",
                    variable=self.config_vars[key],
                    onvalue=True,
                    offvalue=False
                )
                self.widget[key].pack(side="left", fill="x", expand=True)
            else:
                # this will fail, but at least it will fail with a log message.
                log.error(f'No widget defined for variables like {varfunc}')

            self.config_vars[key].trace_add("write", self.reconfig)
            frame.pack(side="top", fill="x", expand=True)

        self.selected_character = selected_character
        self.load_character(self.selected_character.get())
        self.repopulate_options()

    def reconfig(self, *args, **kwargs):
        """
        An engine config value has changed
        """
        if self.loading:
            return
        
        log.info(f'reconfig({args=}, {kwargs=})')
        character = models.get_character_from_rawname(self.selected_character.get())
        
        config = {}
        for cosmetic, key, varfunc, default, cfg, fn in self.CONFIG_TUPLE:
            config[key] = self.config_vars[key].get()
        
        models.set_engine_config(character.id, self.rank, config)
        self.repopulate_options()

    def repopulate_options(self):
        for cosmetic, key, varfunc, default, cfg, fn in self.CONFIG_TUPLE:
            # our change may filter the other widgets, possibly
            # rendering the previous value invalid.
            log.info(f"{cosmetic=} {key=} {default=} {fn=}")
            if fn:
                self.widget[key]["values"] = fn()

    def get_voice_names(self, gender=None):
        if gender and not hasattr(self, 'gender'):
            self.gender = gender

        # cache these to the database, this is crude
        # I haven't even listened to all these, this is best guess
        # from names.  These are the current free-tier voices:
        FEMALE = [
            "Rachel : 21m00Tcm4TlvDq8ikWAM",
            "Sarah : EXAVITQu4vr4xnSDxMaL",
            "Emily : LcfcDJNUP1GQjkzn1xUU",
            "Elli : MF3mGyEYCl7XYWbV9V6O",
            "Dorothy : ThT5KcBeYPX3keUQqHPh",
            "Charlotte : XB0fDUnXU5powFXDhCwa",
            "Alice : Xb7hH8MSUJpSbSDYk0k2",
            "Matilda : XrExE9yKIg1WjnnlVkGX",
            "Gigi : jBpfuIE2acCO8z3wKNLl",
            "Freya : jsCqWAovK2LkecY7zXl4",
            "Grace : oWAxZDx7w5VEj9dCyTzz",
            "Lily : pFZP5JQG7iQjIQuC4Bku",
            "Serena : pMsXgVXv3BLzUgSXRplE",
            "Nicole : piTKgcLEGmPE4e6mEKli",
            "Glinda : z9fAnlkpzviPz146aGWa",
            "Mimi : zrHiDhphv9ZnVXBqCLjz",
        ]
        MALE = [
            "Drew : 29vD33N1CtxCmqQRPOHJ",
            "Clyde : 2EiwWnXFnvU5JabPnv8n",
            "Paul : 5Q0t7uMcjvnagumLfvZi",
            "Domi : AZnzlk1XvdvUeBnXmlld",
            "Dave : CYw3kZ02Hs0563khs1Fj",
            "Fin : D38z5RcWu1voky8WS1ja",
            "Antoni : ErXwobaYiN019PkySvjV",
            "Thomas : GBv7mTt0atIp3Br8iCZE",
            "Charlie : IKne3meq5aSn9XLyUdCD",
            "George : JBFqnCBsd6RMkjVDRZzb",
            "Callum : N2lVS1w4EtoT3dr4eOWO",
            "Patrick : ODq5zmih8GrVes37Dizd",
            "Harry : SOYHLrjzK2X1ezoPC6cr",
            "Liam : TX3LPaxmHKxFdv7VOQHJ",
            "Josh : TxGEqnHWrfWFTfGW9XjX",
            "Arnold : VR6AewLTigWG4xSOukaG",
            "James : ZQe5CZNOzWyzPSCn5a3c",
            "Joseph : Zlb1dXrM653N07WRdFW3",
            "Jeremy : bVMeCyTHy58xNoL34h3p",
            "Michael : flq6f7yk4E4fJM5XTYuZ",
            "Ethan : g5CIjZEefAph4nQFvHAz",
            "Chris : iP95p4xoKVk53GoZ742B",
            "Brian : nPczCjzI2devNBz1zQrb",
            "Daniel : onwK4e9ZLuTAKqWW03F9",
            "Adam : pNInz6obpgDQGcFmaJgB",
            "Bill : pqHfZKP75CvOlQylNhV4",
            "Jessie : t0jbNlBVZ17f02VDIeMI",
            "Sam : yoZ06aMxZJJ28mfd3POQ",
            "Giovanni : zcAOhNBS3c14rBihAFp1",
        ] 

        out = []
        if gender is None:
            out = FEMALE + MALE
        elif gender.upper() == "FEMALE":
            out = FEMALE
        elif gender.upper() == "MALE":
            out = MALE
        else:
            out = FEMALE + MALE

        if out:
            if self.config_vars["voice_name"].get() not in out:
                # our currently selected voice is invalid.  Pick a new one.
                self.config_vars["voice_name"].set(out[0])
            return out
        else:
            return []
                    
        #########
        client = get_elevenlabs_client()
        all_raw_voices = client.voices.get_all()

        all_voices = []
        for voice in all_raw_voices.voices:
            log.info(f"{voice!r}")
            if gender and as_gender(voice.labels.get("gender")) == gender:
                all_voices.append(f"{voice.name} : {voice.voice_id}")
            else:
                if gender is None:
                    all_voices.append(f"{voice.name} : {voice.voice_id}")

                else:
                    log.info("%s?=%s" % (as_gender(voice.labels.get("gender")), gender))

        log.info(all_voices)
        return all_voices

    def get_tts(self):
        # voice is an elevenlabs.Voice instance,  We need input from the user
        # so we add a choice field the __init__
        # model : :class:`elevenlabs.Model` instance, or a string representing the model ID.

        # settings comments from https://elevenlabs.io/docs/speech-synthesis/voice-settings
        voice_name = self.override.get('voice_name', self.config_vars["voice_name"].get())
        
        # The stability slider determines how stable the voice is and the
        # randomness between each generation. Lowering this slider introduces a
        # broader emotional range for the voice. As mentioned before, this is
        # also influenced heavily by the original voice. Setting the slider too
        # low may result in odd performances that are overly random and cause
        # the character to speak too quickly. On the other hand, setting it too
        # high can lead to a monotonous voice with limited emotion.
        stability = self.override.get('stability', self.config_vars["stability"].get())

        # "similarity_boost" corresponds to"Clarity + Similarity Enhancement" in the web app 
        similarity_boost = self.override.get('similarity_boost', self.config_vars["similarity_boost"].get())

        # With the introduction of the newer models, we also added a style
        # exaggeration setting. This setting attempts to amplify the style of
        # the original speaker. It does consume additional computational
        # resources and might increase latency if set to anything other than 0.
        # It’s important to note that using this setting has shown to make the
        # model slightly less stable, as it strives to emphasize and imitate the
        # style of the original voice. In general, we recommend keeping this
        # setting at 0 at all times.
        style = self.override.get('style', self.config_vars["style"].get())

        # This is another setting that was introduced in the new models. The
        # setting itself is quite self-explanatory – it boosts the similarity to
        # the original speaker. However, using this setting requires a slightly
        # higher computational load, which in turn increases latency. The
        # differences introduced by this setting are generally rather subtle.
        use_speaker_boost = self.override.get('use_speaker_boost', self.config_vars["use_speaker_boost"].get())

        # model = elevenlabs.Model()
        model = None
        
        log.info(f'Creating ttsElevenLab(<api_key>, voice={voice_name}, model={model})')
        return ttsElevenLabs(
            api_key=self.api_key, 
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost,
            voice=voice_name,
            model=model
        )

@dataclass
class ttsElevenLabs(voicebox.tts.TTS):
    """
    There was an API update in the elevenlabs client that broke the built in voicebox support.
    """
    api_key: str = None
    voice: Union[str, elevenlabs.Voice] = field(default_factory=lambda: elevenlabs.DEFAULT_VOICE)
    model: Union[str, elevenlabs.Model] = 'eleven_monolingual_v1'
    stability: float = 0.71
    similarity_boost: float = 0.5
    style: float = 0.0
    use_speaker_boost : bool = True

    def get_speech(self, text: StrOrSSML) -> Audio:
        client = get_elevenlabs_client()
        # https://github.com/elevenlabs/elevenlabs-python/blob/main/src/elevenlabs/client.py#L118
        # default response is an iterator providing an mp3_44100_128.
        #
        # I tried asking 11labs for a PCM response (wav),so we don't need to decompress an mp3
        # but the PCM wav format returned by 11labs isn't direcly compatible with the 
        # wav format that the wave library known how to open.
        log.debug(f"self.voice: {self.voice}")
        voice_name, voice_id = self.voice.split(':')
        voice_name = voice_name.strip()
        voice_id = voice_id.strip()

        # I'm not actually clear on what exactly 'model' does.
        # voice_model = None

        audio_data = client.generate(
            text=text, 
            voice=elevenlabs.Voice(
                voice_id=voice_id,
                settings=elevenlabs.VoiceSettings(
                    stability=self.stability,
                    similarity_boost=self.similarity_boost,
                    style=self.style,
                    use_speaker_boost=self.use_speaker_boost
                )
            )
        )

        with tempfile.NamedTemporaryFile() as tmp:
            tmp.close()
            # start with an mp3 file
            mp3filename = tmp.name + ".mp3"
            elevenlabs.save(audio_data, mp3filename)

            return audio.mp3file_to_Audio(mp3filename)


class AmazonPolly(TTSEngine):
    """
    Pricing:
    https://aws.amazon.com/polly/pricing/?p=pm&c=ml&pd=polly&z=4
    I think this could be a really great fit for this
    project with its free million characters of tts per 
    month, and (in 2024) each addition million at highest 
    quality for $16.  If the API can make it clear when
    you cross from free to paid and quality is anywhere
    near elevenlabs.. lets see what we can get.
    """
    cosmetic = "Amazon Polly"

    def __init__(self, parent, rank, selected_character, *args, **kwargs):
        super().__init__(parent, rank, selected_character, *args, **kwargs)
        # tk.variable holding the currently selected characters
        # raw_name.  It will be part of the database persistence
        # for this specific instance of AmazonPolly which will only
        # exist for as long as it takes to make one utterance
        # in the voice of one specific character.  We already know
        # it is an AmazonPolly voice because we wouldn't be the one
        # talking otherwise.  Duhh.
        self.rank = rank
        self.parameters = set(("language_code", "engine", "voice_name", "sample_rate"))

        # what variables does Polly allow/require?
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/polly.html
        
        # what widgets do we need to configure those variables?
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/polly/client/synthesize_speech.html

        self.CONFIG_TUPLE = (
            ('Language Code', 'language_code', 'en-US', self.get_language_codes),
            ('Engine', 'engine', 'standard', self.get_engine_names),
            ('Voice Name', 'voice_name', "<unconfigured>", self.get_voice_names),
            ('Sample Rate', 'sample_rate', '16000', self.get_sample_rates)
        )

        self.config_vars = {}
        self.widget = {}

        for cosmetic, key, default, fn in self.CONFIG_TUPLE:
            frame = ttk.Frame(self)
            ttk.Label(frame, text=cosmetic, anchor="e").pack(
                side="left", fill="x", expand=True
            )
            self.config_vars[key] = tk.StringVar(value=default if default else "")

            self.widget[key] = ttk.Combobox(
                frame,
                textvariable=self.config_vars[key],
            )

            self.widget[key]["state"] = "readonly"
            self.widget[key].pack(side="left", fill="x", expand=True)

            self.config_vars[key].trace_add("write", self.reconfig)
            frame.pack(side="top", fill="x", expand=True)

        self.selected_character = selected_character
        self.load_character(self.selected_character.get())
        self.repopulate_options()

        self.session = boto3.Session()
        self.client = self.session.client('polly')

    def reconfig(self, *args, **kwargs):
        """
        An engine config value has changed
        """
        if self.loading:
            return
        
        log.info(f'reconfig({args=}, {kwargs=})')
        character = models.get_character_from_rawname(self.selected_character.get())
        
        config = {}
        for cosmetic, key, default, fn in self.CONFIG_TUPLE:
            config[key] = self.config_vars[key].get()
        
        models.set_engine_config(character.id, self.rank, config)
        self.repopulate_options()

    def repopulate_options(self):
        for cosmetic, key, default, fn in self.CONFIG_TUPLE:
            # our change may filter the other widgets, possibly
            # rendering the previous value invalid.
            log.info(f"{cosmetic=} {key=} {default=} {fn=}")
            self.widget[key]["values"] = fn()

    def _gender_filter(self, voice):
        if hasattr(self, 'gender') and self.gender:
            # log.info(f"_gender_filter: {self.gender.upper()} ?= {voice['Gender'].upper()}")
            return self.gender.upper() == voice["Gender"].upper()
        log.info('bypassing gender filter')
        return True

    def _language_code_filter(self, voice):
        """
        True if this voice is able to speak this language_code.
        """
        selected_language_code = self.config_vars["language_code"].get()
        return (
            selected_language_code == voice["LanguageCode"]
        or
            selected_language_code in voice.get("AdditionalLanguageCodes", [])
        )

    def get_language_codes(self):
        all_voices = self.get_voices()
        out = set()
        
        for voice_id in all_voices:
            voice = all_voices[voice_id]           

            if self._gender_filter(voice):
                out.add(voice["LanguageCode"])
                for code in voice.get('AdditionalLanguageCodes', []):
                    out.add(code)

        return sorted(list(out))

    def get_engine_names(self, filter_by=None):
        all_voices = self.get_voices()

        out = set()
        # is this going to be intuitive or just weird?
        for voice_id in all_voices:
            voice = all_voices[voice_id]
            if self._language_code_filter(voice) and self._gender_filter(voice):
                for code in voice.get('SupportedEngines', []):
                    out.add(code)

        return sorted(list(out))

    def get_voice_names(self, gender=None):
        all_voices = self.get_voices()
        
        if gender and not hasattr(self, 'gender'):
            self.gender = gender

        out = set()
        for voice_id in all_voices:
            voice = all_voices[voice_id]
            if self._language_code_filter(voice) and self._gender_filter(voice):
                log.info(f'Including voice {voice["Name"]}')
                out.add(f'{voice["Name"]} - {voice["Id"]}')
        
        out = sorted(list(out))
        
        if out:
            if self.config_vars["voice_name"].get() not in out:
                # our currently selected voice is invalid.  Pick a new one.
                self.config_vars["voice_name"].set(out[0])
            return out
        else:
            return []

    def get_sample_rates(self, filter_by=None):
        # what does this depend on?
        # and.. it depends only some internal details in voicebox
        # If we change voicebox to use mp3 or ogg_vorbis we could
        # use [8000, 16000, 22050, 24000] 
        # But since it is getting PCM from Polly the only
        # valid sample rates are:
        return ["8000", "16000"]

    def get_tts(self):
        """
        Returns a voicebox TTS object initialized for a specific
        character
        """
        
        # https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
        #
        # ~/.aws/credentials
        # C:\Users\<UserName>\.aws\credentials
        #
        # [default]
        # aws_access_key_id = YOUR_ACCESS_KEY
        # aws_secret_access_key = YOUR_SECRET_KEY
        #
        # ~/.aws/config:
        # [default]
        # region=us-west-1
        #
        # https://us-east-2.console.aws.amazon.com/polly/home/SynthesizeSpeech
        
        raw_voice_name = self.override.get('voice_name', self.config_vars["voice_name"].get())
        voice_name, voice_id = raw_voice_name.split('-')

        # Engine (string) – Specifies the engine ( standard, neural, long-form or generative) used by Amazon Polly when processing input text for speech synthesis.
        engine = self.config_vars["engine"].get()
        
        # LanguageCode (string) – The language identification tag (ISO 639 code for the language name-ISO 3166 country code) for filtering the list of voices returned. If you don’t specify this optional parameter, all available voices are returned.
        language_code=self.override.get('language_code', self.config_vars["language_code"].get())
        lexicon_names=[]
        sample_rate = self.override.get('sample_rate', self.config_vars["sample_rate"].get())
        
        return AmazonPollyTTS(
            client=self.client,
            voice_id=voice_id.strip(),
            engine=engine,
            language_code=language_code,
            lexicon_names=lexicon_names,
            sample_rate=int(sample_rate)
        )

    def get_voices(self):
        # Language code of the voice.
        # you know, we aren't really interested in listing
        # _every_ language code.  We only want the ones
        # that have at least one Amazon Polly voice.
        all_voices = models.diskcache('amazon_polly_describe_voices')

        if all_voices is None:
            session = boto3.Session()
            client = session.client('polly')

            all_voices = {}
            for voice in client.describe_voices()['Voices']:
                all_voices[voice["Id"]] = voice
            
            models.diskcache('amazon_polly_describe_voices', all_voices)

        return all_voices


# https://github.com/coqui-ai/tts
# I tried this.  Doesn't work yet in Windown w/Py 3.12 due to the 
# absense of compiled pytorch binaries.  I'm more than a little worried
# the resources requirment and speed will make it impractical.

def get_engine(engine_name):
    for engine_cls in ENGINE_LIST:
        if engine_name == engine_cls.cosmetic:
            log.debug(f"found {engine_cls.cosmetic}")
            return engine_cls


ENGINE_LIST = [WindowsTTS, GoogleCloud, ElevenLabs, AmazonPolly ]
