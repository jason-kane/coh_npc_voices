import json
import logging
import os
import sys
import tempfile
import time
import tkinter as tk
from dataclasses import dataclass, field
from io import BytesIO
from tkinter import ttk
from typing import Union

import boto3
import cnv.database.models as models
import cnv.lib.audio as audio
import cnv.lib.settings as settings
import elevenlabs
import numpy as np
import tts.sapi
import voicebox
from elevenlabs.client import ElevenLabs as ELABS
from google.cloud import texttospeech
from sqlalchemy import select
from voicebox.audio import Audio
from voicebox.tts.amazonpolly import AmazonPolly as AmazonPollyTTS
from voicebox.types import StrOrSSML

logging.basicConfig(
    level=settings.LOGLEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger(__name__)


class USE_SECONDARY(Exception):
    """
    signal to disable this engine for this session
    """

@dataclass
class WindowsSapi(voicebox.tts.tts.TTS):
    rate: int = 1
    voice: str = "Zira"

    def get_speech(self, text: StrOrSSML) -> Audio:
        voice = tts.sapi.Sapi()
        log.debug(f"Saying {text!r} as {self.voice} at rate {self.rate}")
        voice.set_rate(self.rate)
        voice.set_voice(self.voice)

        stream = tts.sapi.comtypes.client.CreateObject('SAPI.SpMemoryStream')
        
        # save the original output stream
        temp_stream = voice.voice.AudioOutputStream

        # hijack it
        voice.voice.AudioOutputStream = stream

        voice.say(text)

        # restore it
        voice.voice.AudioOutputStream = temp_stream
        
        samples = np.frombuffer(
            bytes(stream.GetData()), 
            dtype=np.int16
        )

        audio = voicebox.tts.utils.get_audio_from_samples(
            samples,
            22050
        )

        return audio


# Base Class for engines
class TTSEngine(ttk.Frame):
    def __init__(self, parent, rank, name, category, *args, **kwargs):
        log.debug(f'Initializing TTSEngine {parent=} {rank=} {name=} {category=}')
        super().__init__(parent, *args, **kwargs)
        self.rank = rank
        self.parent = parent
        self.name = name
        self.category = category
        self.override = {}
        self.parameters = set('voice_name')
        self.config_vars = {}
        self.widget = {}

        self.set_config_meta(self.config)

        self.draw_config_meta()
        self.load_character(category=category, name=name)
        self.repopulate_options()

    def get_config_meta(self):
        with models.db() as session:
            response = session.scalars(
                select(models.EngineConfigMeta).where(
                    models.EngineConfigMeta.engine_key == self.key
                )
            ).all()
        return response

    def set_config_meta(self, *rows):
        # wipe existing configuration metadata
        with models.db() as session:
            old_settings = session.scalars(
                select(models.EngineConfigMeta).where(
                    models.EngineConfigMeta.engine_key==self.key
                )
            ).all()

            for old_row in old_settings:
                session.delete(old_row)
            session.commit()

        with models.db() as session:
            for row in rows[0]:
                # log.info(f"{row=}")
                cosmetic, key, varfunc, default, cfg, fn = row
                field = models.EngineConfigMeta(
                    engine_key=self.key,
                    cosmetic=cosmetic,
                    key=key,
                    varfunc=varfunc,
                    default=default,
                    cfgdict=cfg,
                    gatherfunc=fn
                )
                session.add(field)
            session.commit()

    def say(self, message, effects, sink=None, *args, **kwargs):
        tts = self.get_tts()
        # log.info(f'{self}.say({message=}, {effects=}, {sink=}, {args=}, {kwargs=}')
        # log.info(f'Invoking voicebox.SimpleVoicebox({tts=}, {effects=}, {sink=})')
        vb = voicebox.SimpleVoicebox(
            tts=tts,
            effects=effects, 
            sink=sink
        )

        if message:

            try:
                vb.say(message)
            except Exception as err:
                log.error('vb: %s', vb)
                log.error("Error in TTSEngine.say(): %s", err)
                if hasattr(err, "grpc_status_code"):
                    # google error
                    #  Error in TTSEngine.say(): 503 failed to connect to all addresses; last error: UNAVAILABLE: ipv4:172.217.12.106:443: WSA Error
                    
                    # this is what happens when you try to use google TTS when
                    # networking is borked.
                    log.error(err)
                    if err.grpc_status_code == 14:
                        raise USE_SECONDARY

                elif err.status_code == 401:
                    log.error(err.body)
                    if err.body.get('detail', {}).get('status') == "quota_exceeded":
                        raise USE_SECONDARY
                raise

    def get_tts(self):
        return voicebox.tts.tts.TTS()

    def load_character(self, category, name):
        # Retrieve configuration settings from the DB
        # and use them to set values on widgets
        # settings.how_did_i_get_here()

        self.loading = True
        self.name = name
        self.category = category
        
        with models.db() as session:
            character = models.Character.get(name, category, session)

        self.gender = settings.get_npc_gender(character.name)
        
        engine_config = models.get_engine_config(character.id, self.rank)

        for key, value in engine_config.items():
            log.debug(f'Setting config {key} to {value}')
            
            # log.info(f"{dir(self)}")
            if hasattr(self, 'config_vars'):
                # the polly way
                log.debug(f'PolyConfig[{key}] = {value}')
                # log.info(f'{self.config_vars=}')
                if key in self.config_vars:
                    self.config_vars[key].set(value)
            else:
                log.error(f'OBSOLETE config[{key}] = {value}')
                # everything else
                getattr(self, key).set(value)
                setattr(self, key + "_base", value)

        # log.info("TTSEngine.load_character complete")
        self.loading = False
        return character

    def save_character(self, name, category):
        # Retrieve configuration settings from widgets
        # and persist them to the DB
        # log.info(f"save_character({name}, {category})")

        character = models.Character.get(name, category)

        if character is None:
            # new character?  This is not typical.
            # log.info(f'Creating new character {name}`')
            
            with models.db() as session:
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

            # log.info("character: %s", character)
            for key in self.parameters:
                # log.info(f"Processing attribute {key}...")
                # do we already have a value for this key?
                value = str(getattr(self, key).get())

                # do we already have a value for this key?
                with models.db() as session:
                    config_setting = session.execute(
                        select(models.BaseTTSConfig).where(
                            models.BaseTTSConfig.character_id == character.id,
                            models.BaseTTSConfig.rank == self.rank,
                            models.BaseTTSConfig.key == key,
                        )
                    ).scalar_one_or_none()

                    if config_setting and config_setting.value != value:
                        log.debug('Updating existing setting')
                        config_setting.value = value
                        session.commit()

                    elif not config_setting:
                        log.debug('Saving new BaseTTSConfig')
                        with models.db() as session:
                            new_config_setting = models.BaseTTSConfig(
                                character_id=character.id, 
                                rank=self.rank,
                                key=key, 
                                value=value
                            )
                            session.add(new_config_setting)
                            session.commit()

    def draw_config_meta(self):
        # now we build it.
        for m in self.get_config_meta():
            frame = ttk.Frame(self)
            frame.columnconfigure(0, minsize=125, uniform="ttsengine")
            frame.columnconfigure(1, weight=2, uniform="ttsengine")
            ttk.Label(frame, text=m.cosmetic, anchor="e").grid(
                row=0, column=0, sticky="e", padx=10
            )

            # create the tk.var for the value of this widget
            varfunc = getattr(tk, m.varfunc)
            self.config_vars[m.key] = varfunc(value=m.default)

            # create the widget itself
            if m.varfunc == "StringVar":
                self._tkStringVar(m.key, frame)
            elif m.varfunc == "DoubleVar":
                self._tkDoubleVar(m.key, frame, m.cfgdict)
            elif m.varfunc == "BooleanVar":
                self._tkBooleanVar(m.key, frame)
            else:
                # this will fail, but at least it will fail with a log message.
                log.error(f'No widget defined for variables like {varfunc}')

            # changes to the value of this widget trip a generic 'reconfig'
            # handler.
            self.config_vars[m.key].trace_add("write", self.reconfig)
            frame.pack(side="top", fill="x", expand=True)

    def _tkStringVar(self, key, frame):
        # combo widget for strings
        self.widget[key] = ttk.Combobox(
            frame,
            textvariable=self.config_vars[key],
        )
        self.widget[key]["state"] = "readonly"
        self.widget[key].grid(row=0, column=1, sticky="ew")

    def _tkDoubleVar(self, key, frame, cfg):
        # doubles get a scale widget.  I haven't been able to get the ttk.Scale
        # widget to behave itself.  I like the visual a bit better, but its hard
        # to get equivilent results.

        self.widget[key] = tk.Scale(
            frame,
            variable=self.config_vars[key],
            from_=cfg.get('min', 0),
            to=cfg['max'],
            orient='horizontal',
            digits=cfg.get('digits', 2),
            resolution=cfg.get('resolution', 1)
        )
        self.widget[key].grid(row=0, column=1, sticky="ew")

    def _tkBooleanVar(self, key, frame):
        """
        Still using a label then checkbutton because the 'text' field on
        checkbutton puts the text after the button.  Well, and it will make it
        easier to maintain consistency with the other widgets.  Oh, and text
        doesn't belong on a checkbox.  It's a wart, sorry.
        """
        self.widget[key] = ttk.Checkbutton(
            frame,
            text="",
            variable=self.config_vars[key],
            onvalue=True,
            offvalue=False
        )
        self.widget[key].grid(row=0, column=1, sticky="ew")

    def reconfig(self, *args, **kwargs):
        """
        Any engine value has been changed.  In most cases this is a single
        change, but it could also be multiple changes.  The changes are between
        the current values in all the UI configuration widgets and the values
        stored in the database.

        We need to persist the changes, but in some cases changes can cascade.
        For example changing the language can change the available voices.  So
        each time a change comes through we shake the knob to see if any of our
        combo widgets need to repopulate.
        """
        if self.loading:
            return
        
        # log.info(f'reconfig({args=}, {kwargs=})')
        with models.db() as session:
            character = models.Character.get(
                name=self.name, 
                category=self.category,
                session=session
            )
    
        config = {}
        for m in self.get_config_meta():
            config[m.key] = self.config_vars[m.key].get()
        
        models.set_engine_config(character.id, self.rank, config)
        self.repopulate_options()

    def repopulate_options(self):
        for m in self.get_config_meta():
            # for cosmetic, key, varfunc, default, cfg, fn in self.CONFIG_TUPLE:
            # our change may filter the other widgets, possibly
            # rendering the previous value invalid.
            if m.varfunc == "StringVar":
                # log.info(f"{m.cosmetic=} {m.key=} {m.default=} {m.gatherfunc=}")
                all_options = getattr(self, m.gatherfunc)()
                if not all_options:
                    log.error(f'{m.gatherfunc=} returned no options ({self.cosmetic})')

                self.widget[m.key]["values"] = all_options
            
                if self.config_vars[m.key].get() not in all_options:
                    # log.info(f'Expected to find {self.config_vars[m.key].get()!r} in list {all_options!r}')                    
                    self.config_vars[m.key].set(all_options[0])
            
    def _gender_filter(self, voice):
        if hasattr(self, 'gender') and self.gender:
            log.debug(f'{self.gender.title()} ?= {voice["gender"].title()}')
            try:
                return self.gender.title() == voice["gender"].title()
            except KeyError:
                log.warning('Failed to find "gender" in:')
                log.debug(f"{voice=}")
        return True


class WindowsTTS(TTSEngine):
    cosmetic = "Windows TTS"
    key = "windowstts"

    VOICE_SUPERSET = {
        'Hoda': {
            'gender': 'Female',
            'language_code': 'arb' # arabic
        },
        'Naayf': {
            'gender': 'Male',
            'language_code': 'ar-SA' # arabic (saudi)
        }, 
        'Ivan': {
            'gender': 'Male',
            'language_code': 'bg-BG' # Bulgarian
        },
        'Herena': {
            'gender': 'Female',
            'language_code': 'ca-ES' # Catalan
        },
        'Kangkang': {
            'gender': 'Male',
            'language_code': 'cmn-CN' # Chinese (simplified)
        },
        'Huihui': {
            'gender': 'Female',
            'language_code': 'cmn-CN' # Chinese (simplified)
        },
        "Yaoyao": {
            'gender': 'Female',
            'language_code': 'cmn-CN' # Chinese (simplified)
        },
        'Danny': {
            'gender': 'Male',
            'language_code': 'yue-CN' # Cantonese (Traditional, Hong Kong SAR)
        },
        'Tracy': {
            'gender': 'Female',
            'language_code': 'yue-CN' # Cantonese (Traditional, Hong Kong SAR)
        },
        'Zhiwei': {
            'gender': 'Male',
            'language_code': 'yue-CN' # Chinese (Traditional, Taiwan)
        },
        'Matej': {
            'gender': 'Male',
            'language_code': 'hr-HR' # Croatian
        },
        'Jakub': {
            'gender': 'Male',
            'language_code': 'cs-CZ' # Czech
        },
        "Helle": {
            'gender': 'Female',
            'language_code': 'da-DK' # Danish
        }, 
        "Frank": {
            'gender': 'Male',
            'language_code': 'nl-NL' # Dutch
        }, 
        "James": {
            'gender': 'Male',
            'language_code': 'en-AU' # English (Australia)
        },
        "Catherine": {
            'gender': 'Female',
            'language_code': 'en-AU' # English (Australia)
        },
        "Richard": {
            'gender': 'Male',
            'language_code': 'en-CA' # English (Canada)
        },
        "Linda": {
            'gender': 'Female',
            'language_code': 'en-CA' # English (Canada)
        },
        "Nathalie": {
            'gender': 'Female',
            'language_code': 'en-CA' # English (Canada) (this might be french, idk)
        },        
        "George": {
            'gender': 'Male',
            'language_code': 'en-GB' # English (GB)
        },
        "Hazel": {
            'gender': 'Female',
            'language_code': 'en-GB' # English (GB)
        },
        "Susan": {
            'gender': 'Female',
            'language_code': 'en-GB' # English (GB)
        },
        "Ravi": {
            'gender': 'Male',
            'language_code': 'en-IN' # English (India)
        },
        "Heera": {
            'gender': 'Female',
            'language_code': 'en-IN' # English (India)
        },
        "Sean": {
            'gender': 'Male',
            'language_code': 'en-IE' # English (Ireland)
        },
        "David": {
            'gender': 'Male',
            'language_code': 'en-US' # English (US)
        },
        "Mark": {
            'gender': 'Male',
            'language_code': 'en-US' # English (US)
        },
        "Zira": {
            'gender': 'Female',
            'language_code': 'en-US' # English (US)
        },
        "Heidi": {
            'gender': 'Female',
            'language_code': 'fi-FL' # Finnish
        },
        "Bart": {
            'gender': 'Male',
            'language_code': 'nl-BE' # Flemish (Belgian Dutch)
        },
        "Claude": {
            'gender': 'Male',
            'language_code': 'fr-CA' # French (Canadian)
        },
        "Caroline": {
            'gender': 'Female',
            'language_code': 'fr-CA' # French (Canadian)
        },
        "Paul": {
            'gender': 'Male',
            'language_code': 'fr-FR' # French
        },
        "Hortense": {
            'gender': 'Female',
            'language_code': 'fr-FR' # French
        },
        "Julie": {
            'gender': 'Female',
            'language_code': 'fr-FR' # French
        },
        "Guillaume": {
            'gender': 'Male',
            'language_code': 'fr-CH' # French (Switzerland)
        },
        "Michael": {
            'gender': 'Male',
            'language_code': 'de-AT' # German (Austria)
        },
        "Stefan": {
            'gender': 'Male',
            'language_code': 'de-DE' # German
        },
        "Hedda": {
            'gender': 'Female',
            'language_code': 'de-DE' # German
        },
        "Katja": {
            'gender': 'Female',
            'language_code': 'de-DE' # German
        },
        "Karsten": {
            'gender': 'Male',
            'language_code': 'de-CH' # German (Switzerland)
        },
        "Stefanos": {
            'gender': 'Male',
            'language_code': 'el-GR' # Greek
        },
        "Asaf": {
            'gender': 'Male',
            'language_code': 'he-IL' # Hebrew
        },
        "Hemant": {
            'gender': 'Male',
            'language_code': 'hi-IN' # Hindi (India)
        },
        "Kalpana": {
            'gender': 'Female',
            'language_code': 'hi-IN' # Hindi (India)
        },
        "Szabolcs": {
            'gender': 'Male',
            'language_code': 'hu-HU' # Hungarian
        },
        "Andika": {
            'gender': 'Male',
            'language_code': 'id-ID' # Indonesian
        },
        "Cosimo": {
            'gender': 'Male',
            'language_code': 'it-IT' # Italian
        },
        "Elsa": {
            'gender': 'Female',
            'language_code': 'it-IT' # Italian
        },
        "Ichiro": {
            'gender': 'Male',
            'language_code': 'ja-JP' # Japanese
        },
        "Sayaka": {
            'gender': 'Male',
            'language_code': 'ja-JP' # Japanese
        },
        "Ayumi": {
            'gender': 'Female',
            'language_code': 'ja-JP' # Japanese
        },
        "Haruka": {
            'gender': 'Female',
            'language_code': 'ja-JP' # Japanese
        },
        "Rizwan": {
            'gender': 'Male',
            'language_code': 'ms-MY' # Malay
        },
        "Jon": {
            'gender': 'Male',
            'language_code': 'nb-NO' # Norwegian
        },
        "Adam": {
            'gender': 'Male',
            'language_code': 'pl-PL' # Polish
        },
        "Paulina": {
            'gender': 'Female',
            'language_code': 'pl-PL' # Polish
        },
        "Daniel": {
            'gender': 'Male',
            'language_code': 'pt-BR' # Portuguese (Brazil)
        },
        "Maria": {
            'gender': 'Female',
            'language_code': 'pt-BR' # Portuguese (Brazil)
        },
        "Helia": {
            'gender': 'Female',
            'language_code': 'pt-PT' # Portuguese
        },
        "Andrei": {
            'gender': 'Male',
            'language_code': 'ro-RO' # Romanian
        },
        "Pavel": {
            'gender': 'Male',
            'language_code': 'ru-RU' # Russian
        },
        "Irina": {
            'gender': 'Female',
            'language_code': 'ru-RU' # Russian
        },
        "Filip": {
            'gender': 'Male',
            'language_code': 'sk-SK' # Slovak
        },
        "Lado": {
            'gender': 'Male',
            'language_code': 'hu-SL' # Slovenian
        },
        "Heami": {
            'gender': 'Female',
            'language_code': 'ko-KR' # Korean
        },
        "Pablo": {
            'gender': 'Male',
            'language_code': 'es-ES' # Spanish (Spain)
        },
        "Helena": {
            'gender': 'Female',
            'language_code': 'es-ES' # Spanish (Spain)
        },        
        "Laura": {
            'gender': 'Female',
            'language_code': 'es-ES' # Spanish (Spain)
        },        
        "Raul": {
            'gender': 'Male',
            'language_code': 'es-MX' # Spanish (Mexico)
        },
        "Sabina": {
            'gender': 'Female',
            'language_code': 'es-MX' # Spanish (Mexico)
        },        
        "Bengt": {
            'gender': 'Male',
            'language_code': 'sv-SE' # Swedish
        },
        "Valluvar": {
            'gender': 'Male',
            'language_code': 'ta-IN' # Tamil
        },
        "Pattara": {
            'gender': 'Male',
            'language_code': 'th-TH' # Thai
        },
        "Tolga": {
            'gender': 'Male',
            'language_code': 'tr-TR' # Turkish
        },
        "An": {
            'gender': 'Male',
            'language_code': 'vi-VN' # Vietnamese
        },
    }

    config = (
        ('Voice Name', 'voice_name', "StringVar", "<unconfigured>", {}, "get_voice_names"),
        ('Speaking Rate', 'rate', "DoubleVar", 1, {'min': -3.5, 'max': 3.5, 'digits': 2, 'resolution': 0.5}, None)
    )

    def get_tts(self):
        """
        Return a pre-configured tts class instance
        """
        rate = int(self.override.get('rate', self.config_vars["rate"].get()))
        voice_name = self.override.get('voice_name', self.config_vars["voice_name"].get())
        return WindowsSapi(rate=rate, voice=voice_name)

    def name_to_gender(self, name):
        if name in self.VOICE_SUPERSET:
            return self.VOICE_SUPERSET[name]["gender"]        
        return 'Neutral'

    def get_voice_names(self, gender=None):
        """
        return a sorted list of available voices
        I don't know how much this list will vary
        from windows version to version and from
        machine to machine.
        """
        log.debug(f'Retrieving TTS voice names filtered to only show gender {self.gender}')
        # all_voices = models.diskcache(f"{self.key}_voice_name")
        all_voices = None

        if all_voices is None:
            all_voices = []
            wintts = tts.sapi.Sapi()
            voices = wintts.get_voice_names()
            for v in voices:
                if "Desktop" in v:
                    continue

                name = " ".join(v.split("-")[0].split()[1:])
                if name in self.VOICE_SUPERSET:
                    all_voices.append({
                        'voice_name': name,
                        'gender': self.name_to_gender(name),
                        'language_code': self.VOICE_SUPERSET[name]['language_code']
                    })
                else:
                    all_voices.append({
                        'voice_name': name,
                        'gender': self.name_to_gender(name)
                    })
            
            models.diskcache(f"{self.key}_voice_name", all_voices)
      
        allowed_language_codes = settings.get_voice_language_codes()
        nice_names = []

        for voice in all_voices:
            if gender and voice['gender'] != gender:
                continue
            
            # filter out voices that are not compatible with our language
            if 'language_code' in voice:
                found = False
                for code in allowed_language_codes:
                    if f"{code}-" in voice['language_code']:
                        found = True
                    else:
                        log.debug(f"{code}- not found in {voice['language_code']}")

                if not found:
                    continue
            
            nice_names.append(voice["voice_name"])

        return sorted(nice_names)


class GoogleCloud(TTSEngine):
    cosmetic = "Google Text-to-Speech"
    key = 'googletts'
    
    config = (
        ('Voice Name', 'voice_name', "StringVar", "<unconfigured>", {}, "get_voice_names"),
        ('Speakin Rate', 'speaking_rate', "DoubleVar", 1, {'min': 0.5, 'max': 1.75, 'digits': 3, 'resolution': 0.25}, None),
        ('Voice Pitch', 'voice_pitch', "DoubleVar", 1, {'min': -10, 'max': 10, 'resolution': 0.5}, None)
    )   

    def _language_code_filter(self, voice):
        """
        True if this voice is able to speak this language_code.
        """
        allowed_language_codes = settings.get_voice_language_codes()           

        # two letter code ala: en, and matches against en-whatever
        for allowed_code in allowed_language_codes:
            if any(f"{allowed_code}-" in code for code in voice["language_codes"]):
                log.debug(f'{allowed_code=} matches with {voice["language_codes"]=}')
                return True
        return False

    def get_voice_names(self, gender=None):
        all_voices = self.get_voices()

        if gender and not hasattr(self, 'gender'):
            self.gender = gender
        
        out = set()
        for voice in all_voices:
            if self._language_code_filter(voice):
                if self._gender_filter(voice):
                    out.add(voice['voice_name'])
        
        if not out:
            log.error(f'There are no voices available with language={self.language_code} and gender={self.gender}')
        
        out = sorted(list(out))

        if out:
            voice_name = self.config_vars["voice_name"].get()
            if voice_name not in out:
                # our currently selected voice is invalid.  Pick a new one.
                log.error(f'Voice {voice_name} is now invalid')
                self.config_vars["voice_name"].set(out[0])
            return out
        else:
            return []

    def get_voices(self):
        all_voices = models.diskcache(f'{self.key}_voice_name')

        if all_voices is None:
            client = texttospeech.TextToSpeechClient()
            req = texttospeech.ListVoicesRequest()
            resp = client.list_voices(req)
            all_voices = []
            for voice in resp.voices:
                # log.info(f'{voice.language_codes=}')
                # log.info(dir(voice.language_codes))

                language_codes = []
                for code in voice.language_codes:
                    # log.info(f'{code=}')
                    language_codes.append(code)
                row = {
                    'voice_name': voice.name,
                    'natural_sample_rate_hertz': voice.natural_sample_rate_hertz,
                    'gender': {1: 'Female', 2: 'Male'}[voice.ssml_gender.value],
                    'language_codes': language_codes
                }
                # log.info(f'{row=}')
                # for key in row:
                #    log.info(f'{key} == {json.dumps(row[key])}')

                all_voices.append(row)
            
            models.diskcache(f'{self.key}_voice_name', all_voices)

        return all_voices

    @staticmethod
    def get_voice_gender(voice_name):
        with models.db() as session:
            ssml_gender = session.scalars(
                select(models.GoogleVoices.ssml_gender).where(
                    models.GoogleVoices.name == voice_name
                )
            ).first()
        return ssml_gender

    def get_voice_language(self, voice_name):
        """
        first compatible language code
        """
        allowed_language_codes = settings.get_voice_language_codes()

        all_voices = self.get_voices()
        for voice in all_voices:
            if voice["voice_name"] == voice_name:
                for code in voice['language_codes']:
                    for allowed in allowed_language_codes:
                        if f"{allowed}-" in code:
                            return code
        return None

    def get_tts(self):
        voice_name = self.override.get('voice_name', self.config_vars["voice_name"].get())
        speaking_rate = self.override.get('speaking_rate', self.config_vars["speaking_rate"].get())
        voice_pitch = self.override.get('voice_pitch', self.config_vars["voice_pitch"].get())
        language_code = self.get_voice_language(voice_name)

        client = texttospeech.TextToSpeechClient()

        audio_config = texttospeech.AudioConfig(
            speaking_rate=float(speaking_rate), 
            pitch=float(voice_pitch)
        )

        voice_params = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
        )

        return voicebox.tts.GoogleCloudTTS(
            client=client, 
            voice_params=voice_params, 
            audio_config=audio_config
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
        log.warning("Elevenlabs Requires valid eleven_labs.key file")


def as_gender(in_gender):
    if in_gender in ["female"]:
        return "female"
    if in_gender in ["male"]:
        return "male"
    else:
        return "neutral"

    return in_gender


class ElevenLabs(TTSEngine):
    """
    Elevenlabs detects the incoming language; so in theory every voice works with every language.  I have doubts.
    """
    cosmetic = "Eleven Labs"
    key = "elevenlabs"
    api_key = None

    config = (
        ('Voice Name', 'voice_name', "StringVar", "<unconfigured>", {}, "get_voice_names"),
        ('Stability', 'stability', "DoubleVar", 0.5, {'min': 0, 'max': 1, 'resolution': 0.025}, None),
        ('Similarity Boost', 'similarity_boost', "DoubleVar", 0, {'min': 0, 'max': 1, 'resolution': 0.025}, None),
        ('Style', 'style', "DoubleVar", 0.0, {'min': 0, 'max': 1, 'resolution': 0.025}, None),
        ('Speaker Boost', 'use_speaker_boost', "BooleanVar", True, {}, None)
    )

    def get_voice_names(self, gender=None):
        """
        PSA, I know there is a lot of gender in this code.  The intention is to
        better guess which voice from an assortment of voices aligns with the
        expections of the person playing the game.  Adding voices in games is a
        great power and it comes with a great responsibility.

        Make lord recluse sound like a little girl? give statesman a heavy lisp?
        all the 5th column a strong german accent? all the street punks an
        enthic voice?
        
        This is a weapon.  To avoid weilding it we set a simple rule. The goal
        is the voice that best presents a realistic interpretation of what each
        character ought to sound like based on the description, appearance and
        dialog. 

        TODO: we need to add a 'cache expire' button on the config for each of
        primary/secondary.
        """
        all_voices = self.get_voices()

        if gender and not hasattr(self, 'gender'):
            self.gender = gender
        
        # log.info(f'ElevenLabs get_voice_name({gender=}) ({self.gender})')
        out = set()
        for voice in all_voices:
            if self._gender_filter(voice):
                out.add(voice['voice_name'])
        
        out = sorted(list(out))

        if out:
            if self.config_vars["voice_name"].get() not in out:
                # our currently selected voice is invalid.  Pick a new one.
                log.error('Invalid voice selecton: %s.  Overriding...', self.config_vars["voice_name"].get())
                self.config_vars["voice_name"].set(out[0])
            return out
        else:
            return []

    def get_voices(self):
        all_voices = models.diskcache(f'{self.key}_voice_name')

        if all_voices is None:
            client = get_elevenlabs_client()
            all_raw_voices = client.voices.get_all()

            all_voices = []
            for voice in all_raw_voices.voices:
                # log.info(f"{voice=}")
                all_voices.append({
                    'id': voice.voice_id,
                    'voice_name': voice.name,
                    'gender': voice.labels['gender'].title()
                })
       
            # log.info(all_voices)
            models.diskcache(f'{self.key}_voice_name', all_voices)
        
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
        
        # log.info(f'Creating ttsElevenLab(<api_key>, voice={voice_name}, model={model})')
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

    def voice_name_to_id(self, voice_name):
        voice_name = voice_name.strip()
        for voice in models.diskcache(f'elevenlabs_voice_name'):
            if voice['voice_name'] == voice_name:
                return voice['id']

        log.error('Unknown voice:  %s', voice_name)

    def get_speech(self, text: StrOrSSML) -> Audio:
        client = get_elevenlabs_client()
        # https://github.com/elevenlabs/elevenlabs-python/blob/main/src/elevenlabs/client.py#L118
        # default response is an iterator providing an mp3_44100_128.
        #
        # I tried asking 11labs for a PCM response (wav),so we don't need to decompress an mp3
        # but the PCM wav format returned by 11labs isn't direcly compatible with the 
        # wav format that the python wave library known how to open.
        log.debug(f"self.voice: {self.voice}")
        
        voice_id = self.voice_name_to_id(self.voice)

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
    key = "amazonpolly"

    config = (
        ('Engine', 'engine', "StringVar", 'standard', {}, "get_engine_names"),
        ('Voice Name', 'voice_name', "StringVar", "<unconfigured>", {}, "get_voice_names"),
        ('Sample Rate', 'sample_rate', "StringVar", '16000', {}, "get_sample_rates")
    )
    client = None

    def get_client(self):
        if self.client:
            return self.client
        
        self.session = boto3.Session()
        self.client = self.session.client('polly')
        return self.client       

    def _language_code_filter(self, voice):
        """
        True if this voice is able to speak this language_code.
        """
        allowed_language_codes = settings.get_voice_language_codes()     
        
        for allowed_code in allowed_language_codes:
            if (
                f"{allowed_code}-" in voice["LanguageCode"]
            ):
                #or
                #f"{allowed_code}-" in code for code in voice.get("AdditionalLanguageCodes", [])
            #):
                log.debug(f'{voice["LanguageCode"]=}/{voice.get('AdditionalLanguageCodes', [])} is allowed for {allowed_code=}')
                return True
        return False

    def get_language_codes(self):
        all_language_codes = models.diskcache(f'{self.key}_language_code')

        if all_language_codes is None:
            # log.info('Building AmazonPolly language_code cache')
            all_voices = self.get_voices()
            out = set()
            
            for voice_id in all_voices:
                voice = all_voices[voice_id]           

                if self._gender_filter(voice):
                    out.add(voice["LanguageCode"])
                    for code in voice.get('AdditionalLanguageCodes', []):
                        out.add(code)

            all_language_codes = [ {'language_code': code} for code in out]
            models.diskcache(f'{self.key}_language_code', all_language_codes)

        # any filtering needed for language codes?
        codes = [code['language_code'] for code in all_language_codes]

        return codes

    def get_engine_names(self):
        all_engines = models.diskcache(f'{self.key}_engine')
        
        if all_engines is None:
            all_voices = self.get_voices()

            out = set()
            secondary = set()
            # is this going to be intuitive or just weird?
            for voice in all_voices:

                if self._language_code_filter(voice):
                    if self._gender_filter(voice):
                        for code in voice.get('SupportedEngines', []):
                            out.add(code)
                    else:
                        for code in voice.get('SupportedEngines', []):
                            secondary.add(code)
            
            if not out:
                log.warning('No engines exist that support this language/gender.  Ignoring gender.')
                out = secondary

            all_engines = [ {'engine': engine_name} for engine_name in out ]
            models.diskcache(f'{self.key}_engine', all_engines)

        return [engine['engine'] for engine in all_engines]

    def get_voice_names(self, gender=None):
        all_voices = self.get_voices()
        
        if gender and not hasattr(self, 'gender'):
            self.gender = gender

        out = set()
        secondary = set()
        for voice in all_voices:
            if self._language_code_filter(voice):
                if self._gender_filter(voice):
                    log.debug(f'Including voice {voice["Name"]}')
                    out.add(voice["Name"])
                else:
                    secondary.add(voice["Name"])
            else:
                log.debug(f'Excluding {voice["Name"]}')

        if not out:
            log.warning('No voices exist that support this language/gender.  Ignoring gender.')
            out = secondary

        out = sorted(list(out))
        
        if out:
            if self.config_vars["voice_name"].get() not in out:
                # our currently selected voice is invalid.  Pick a new one.
                self.config_vars["voice_name"].set(out[0])
            return out
        else:
            return []

    def voice_name_to_voice_id(self, voice_name):
        voice_name = voice_name.strip()
        all_voices = self.get_voices()
        for voice in all_voices:
            if voice['Name'] == voice_name:
                return voice['Id']

        log.error(f'Could not convert {voice_name=} to a voice_id')
        return None

    def get_sample_rates(self, filter_by=None):
        # what does this depend on?
        # and.. it depends only some internal details in voicebox
        # If we change voicebox to use mp3 or ogg_vorbis we could
        # use [8000, 16000, 22050, 24000] 
        # But since it is getting PCM from Polly the only
        # valid options are 8000 and 16000.

        # why is this being cached?  stupid?  ridiculous?
        # this lets us treat all stringvar fields the same way, so yes, but no.
        all_sample_rates = models.diskcache(f'{self.key}_sample_rate')

        if all_sample_rates is None:
            all_sample_rates = [
                {"sample_rate": "8000"}, 
                {"sample_rate": "16000"}
            ]
            models.diskcache(f'{self.key}_sample_rate', all_sample_rates)
        
        return [ rate['sample_rate'] for rate in all_sample_rates ]

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
        voice_id = self.voice_name_to_voice_id(raw_voice_name)

        # Engine (string) – Specifies the engine ( standard, neural, long-form
        # or generative) used by Amazon Polly when processing input text for
        # speech synthesis.
        engine = self.config_vars["engine"].get()
        
        # LanguageCode (string) – The language identification tag (ISO 639 code
        # for the language name-ISO 3166 country code) for filtering the list of
        # voices returned. If you don’t specify this optional parameter, all
        # available voices are returned.
        # language_code=self.override.get('language_code', self.config_vars["language_code"].get())
        lexicon_names=[]
        sample_rate = self.override.get('sample_rate', self.config_vars["sample_rate"].get())
        
        return AmazonPollyTTS(
            client=self.get_client(),
            voice_id=voice_id.strip(),
            engine=engine,
            # language_code=language_code,
            lexicon_names=lexicon_names,
            sample_rate=int(sample_rate)
        )

    def get_voices(self):
        # Language code of the voice.

        # We aren't really interested in listing _every_ language code.  We only
        # want the ones that have at least one Amazon Polly voice.
        all_voices = models.diskcache(f'{self.key}_voice_name')

        if all_voices is None:
            session = boto3.Session()
            client = session.client('polly')

            all_voices = []
            for voice in client.describe_voices()['Voices']:
                log.debug(f'{voice=}')
                voice['voice_name'] = voice["Name"]
                voice['language_code'] = voice["LanguageCode"]
                voice['gender'] = voice["Gender"]
                all_voices.append(voice)
            
            models.diskcache(f'{self.key}_voice_name', all_voices)

        return all_voices


# https://github.com/coqui-ai/tts
# I tried this.  Doesn't work yet in Windown w/Py 3.12 due to the absense of
# compiled pytorch binaries.  I'm more than a little worried the resources
# requirment and speed will make it impractical.

def get_engine(engine_name):
    for engine_cls in ENGINE_LIST:
        if engine_name == engine_cls.cosmetic:
            log.debug(f"found {engine_cls.cosmetic}")
            return engine_cls


ENGINE_LIST = [ WindowsTTS, GoogleCloud, ElevenLabs, AmazonPolly ]
