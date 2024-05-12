import json
import logging
import os
import sys
import tempfile
import time
import random
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Union

import elevenlabs
import models
import settings
import tts.sapi
import voicebox
from elevenlabs.client import ElevenLabs as ELABS
from google.cloud import texttospeech
from pedalboard.io import AudioFile
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
    def __init__(self, parent, selected_character, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
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
                    error_response = json.loads(err.body)
                    if error_response.get('detail', {}).get('status') == "quota_exceeded":
                        raise DISABLE_ENGINES
                raise

    def get_tts(self):
        return voicebox.tts.tts.TTS()

    def load_character(self, raw_name):
        # Retrieve configuration settings from the DB
        # and use them to set values on widgets
        log.info(f"TTSEngine.load_character({raw_name})")
        if raw_name:
            category, name = raw_name.split(maxsplit=1)
        else:
            # I think the only way to get here is by
            # trying to play voices before you've ever
            # attached to the game log.  
            category = 'system'
            name = None

        character = models.get_character(name, category)

        if character is None:
            log.info("No engine configuration available in the database")
            return

        if character.engine == self.cosmetic:
            with models.Session(models.engine) as session:
                tts_config = session.scalars(
                    select(models.BaseTTSConfig).where(
                        models.BaseTTSConfig.character_id == character.id
                    )
                ).all()

                for config in tts_config:
                    log.info(f'Setting config {config.key} to {config.value}')
                    log.info(f'{self} supports parameters {self.parameters}')
                    if config.key in self.parameters:
                        getattr(self, config.key).set(config.value)
                        setattr(self, config.key + "_base", config.value)
        else:
            # Unusual situation.  We are trying to use the "wrong" tts engine
            # for this character. That means we also have the wrong
            # BaseTTSConfig and .. we don't want to mess with the existing
            # configuration.  Oh, and it should still mostly work and be
            # consistent. Use case for this nonesense?
            #
            # You're rolling with Elevenlabs and you run out of free voice
            # credits.  We want to smoothly transition to Google voices.  When
            # Elevenlabs starts working again, we don't want the voice configs
            # to be messed up.
            #
            # we keep effects, that part is easy.
            
            gender = settings.get_npc_gender(character.name)
            
            # we can't do random, because we want a _consistent_ voice.  No
            # problem. gendered_voices should be identical from one "run" to the
            # next.
            gendered_voices = sorted(self.get_voice_names(gender=gender))
            
            # when is random not random?  We don't even need to hash it,
            # random.seed now takes an int (obv) _or_ a str/bytes/bytearray.  
            random.seed(a=character.name, version=2)
            
            # easy as that.  gendered voice name chosen with a good spread of
            # all available voice names, and the same character speaking twice
            # gets the same voice.  Even across sessions.  Even across upgrades.
            voice_name = random.choice(gendered_voices)

            # if we self.voice_name.set(voice_name) the way that feels natural
            # we're going to reconfigure the character in exactly the way we
            # don't want. Jumbo-dict of reasonable choices for all engines. this
            # is clearly unsustainable.  I'm thinking each character and preset
            # gets a full primary and secondary voice config.
            self.override['voice_name'] = voice_name
            self.override['rate'] = 1
            self.override['stabiity'] = 0.71
            self.override['similarity_boost'] = 0.5
            self.override['style'] = 0.0
            self.override['use_speaker_boost'] = True

        log.info("TTSEngine.load_character complete")
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

    def __init__(self, parent, selected_character, *args, **kwargs):
        super().__init__(parent, selected_character, *args, **kwargs)

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
        
        self.voice_name = tk.StringVar(value="")

        self.parameters = ("voice_name",)
        raw_name = self.selected_character.get()

        character = self.load_character(raw_name)
        gender = settings.get_npc_gender(character.name)

        voice_frame = ttk.Frame(self)
        ttk.Label(voice_frame, text="Voice", anchor="e").pack(
            side="left", fill="x", expand=True
        )

        voice_combo = ttk.Combobox(
            voice_frame,
            textvariable=self.voice_name,
        )
        all_voices = ElevenLabs.get_voice_names(gender=gender)
        log.info(f"Assinging all_voices to {all_voices}")
        voice_combo["values"] = all_voices
        voice_combo["state"] = "readonly"
        voice_combo.pack(side="left", fill="x", expand=True)
        voice_frame.pack(side="top", fill="x", expand=True)
        self.voice_name.set(value=all_voices[0])

        self.voice_name.trace_add("write", self.change_voice_name)

        # doing these all long-hand will be tedious
        self.stability = tk.DoubleVar(value=0.71)
        self.similarity_boost = tk.DoubleVar(value=0.5)
        self.style = tk.DoubleVar(value=0.0)
        self.use_speaker_boost = tk.BooleanVar(value=True)

    def change_voice_name(self, a, b, c):
        raw_voice_name = self.voice_name.get()
        log.info('change_voice_name() value=%s', raw_voice_name)

        voice_name, voice_id = raw_voice_name.split(":")
        
        voice_name = voice_name.strip()
        voice_id = voice_id.strip()
        with models.Session(models.engine) as session:
            self.voice = session.execute(
                select(models.ElevenLabsVoices).where(
                    models.ElevenLabsVoices.voice_id == voice_id
                )
            ).scalar_one_or_none()

            if self.voice:
                log.info(f'Setting voice_id to {voice_id}')
                if self.voice.voice_id != voice_id:
                    self.voice.voice_id = voice_id
                    session.commit()
            else:
                log.info('The voice %s does not exist', voice_id)
                new_voice = models.ElevenLabsVoices(
                    voice_id=voice_id,
                    name=voice_name
                )
                session.add(new_voice)
                session.commit()
                session.refresh(new_voice)

                self.voice = new_voice

        self.save_character(self.selected_character.get())

    @staticmethod
    def get_voice_names(gender=None):
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
        if gender is None:
            return FEMALE + MALE
        elif gender.upper() == "FEMALE":
            return FEMALE
        elif gender.upper() == "MALE":
            return MALE
        else:
            return FEMALE + MALE
                    
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
        voice_name = self.override.get('voice_name', self.voice_name.get())
        stability = self.override.get('stability', self.stability.get())
        similarity_boost = self.override.get('similarity_boost', self.similarity_boost.get())
        style = self.override.get('style', self.style.get())
        use_speaker_boost = self.override.get('use_speaker_boost', self.use_speaker_boost.get())

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
        # but if we ask for a PCM response, we don't need to decompress an mp3
        log.info(f"self.voice: {self.voice}")
        voice_name, voice_id = self.voice.split(':')
        voice_name = voice_name.strip()
        voice_id = voice_id.strip()

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
            elevenlabs.save(audio_data, tmp.name + ".mp3")

            log.info('Converting from mp3 to wav...')
            with AudioFile(tmp.name + ".mp3") as input:
                with AudioFile(
                    filename=tmp.name + ".wav", 
                    samplerate=input.samplerate,
                    num_channels=input.num_channels
                ) as output:
                    while input.tell() < input.frames:
                        output.write(input.read(1024))
                    log.info(f'Wrote {tmp.name}.wav')

        # audio_data is a generator returning
        # bytes.  We want an Audio(), which is 
        # a class with signal and sample_rate attributes.
        #
        #with BytesIO(b"".join(audio_data)) as wav_file:
            return voicebox.tts.utils.get_audio_from_wav_file(
                tmp.name + ".wav"
            )
        
        
            tmp.close()

            elevenlabs.save(audio_data, tmp.name)
        
            audio = voicebox.tts.utils.get_audio_from_wav_file(tmp.name)
        
        return audio

        # asBytes = bytes(audio_data)
        # wavfile = BytesIO(asBytes)
        # as_wave = wave.open(wavfile)

        # bytes_per_sample = as_wave.getsampwidth()
        # sample_bytes = as_wave.readframes(-1)
        # sample_rate = as_wave.getframerate()

        # dtype = voicebox.tts.utils.sample_width_to_dtype[bytes_per_sample]
        # samples = numpy.frombuffer(sample_bytes, dtype=dtype)

        # return voicebox.tts.utils.get_audio_from_samples(samples, sample_rate)


class AmazonPolly(TTSEngine):
    cosmetic = "Amazon Polly"

    def __init__(self, parent, selected_character, *args, **kwargs):
        super().__init__(parent, selected_character, *args, **kwargs)


# https://github.com/coqui-ai/tts


def get_engine(engine_name):
    for engine_cls in ENGINE_LIST:
        if engine_name == engine_cls.cosmetic:
            print(f"found {engine_cls.cosmetic}")
            return engine_cls


ENGINE_LIST = [WindowsTTS, GoogleCloud, ElevenLabs]  # AmazonPolly ]
