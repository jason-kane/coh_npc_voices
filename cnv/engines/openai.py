import logging
import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Union

import customtkinter as ctk
import numpy as np
import voicebox
from openai import OpenAI as OAI
from voicebox.audio import Audio
from voicebox.types import StrOrSSML

from cnv.lib.settings import diskcache

from .base import MarkdownLabel, TTSEngine, registry

log = logging.getLogger(__name__)

OPENAI_KEY_FILE = "openai.key"

class OpenAIAuthUI(ctk.CTkFrame):
    label = "OpenAI"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        mdlabel = MarkdownLabel(
            self,
            text="[OpenAI](https://openai.com/) The quality of the OpenAI voices "
            "is really excellent.  Costs are on the high end at $0.015 per 1,000 "
            "input characters. ie: $15 per million characters\n"
            "It is easy to put a hard limit on how much you want to spend. "
            "The variety of voices is extremely limited (there are 6).  I think "
            "this is a great choice for the most important snippets of NPC dialog "
            "where having a few high quality unique voices in reserve pays off.",
            messages_enabled=False
        )
        mdlabel.pack(side="top", fill="x", expand=False)

        auth_settings = ctk.CTkFrame(self)
        auth_settings.columnconfigure(0, minsize=125, weight=0, uniform="baseconfig")
        auth_settings.columnconfigure(1, weight=2, uniform="baseconfig")

        ctk.CTkLabel(
            auth_settings,
            text="OpenAI API Key",
            anchor="e",
        ).grid(column=0, row=0, sticky='e')
        
        self.openai_key = tk.StringVar(value=self.get_openai_key())
        self.openai_key.trace_add('write', self.change_openai_key)
        
        ctk.CTkEntry(
            auth_settings,
            textvariable=self.openai_key,
            show="*"
        ).grid(column=1, row=0, sticky='ew')
        auth_settings.pack(side="top", fill="x", expand=True)

    def change_openai_key(self, a, b, c):
        with open(OPENAI_KEY_FILE, 'w') as h:
            h.write(self.openai_key.get())

    def get_openai_key(self):
        value = None

        if os.path.exists(OPENAI_KEY_FILE):
            with open(OPENAI_KEY_FILE, 'r') as h:
                value = h.read()
        return value


# female = ['alloy, 'nova', 'shimmer']
# male = ['echo', 'onyx']
# neutral = ['fable']
class OpenAI(TTSEngine):
    """
    OpenAI detects the incoming language; so in theory every voice works with every language.  I have doubts.
    """
    cosmetic = "OpenAI"
    key = "openai"
    auth_ui_class = OpenAIAuthUI

    config = (
        ('Voice Name', 'voice_name', "StringVar", "<unconfigured>", {}, "get_voice_names"),
        ('Voice Model', 'model', "StringVar", "<unconfigured>", {}, "get_models"),
        ('Speed', 'speed', "DoubleVar", 1.0, {'min': 0.25, 'max': 4.0, 'resolution': 0.25}, None),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # force the voice table to be populated
        self.get_voices()


    def get_models(self):
        all_models = diskcache(
            f"{self.key}_model"
        )
        if all_models is None:
            all_models = diskcache(
                f"{self.key}_model", [
                    {'model': 'tts-1'},
                    {'model': 'tts-1-hd'}
                ]
            )
        return [k['model'] for k in all_models]

    def get_voices(self) -> list:
        all_voices = diskcache(
            f"{self.key}_voice_name"
        )

        if all_voices is None:
            all_voices = diskcache(
                f"{self.key}_voice_name", [
            {'voice_name': 'alloy', 'gender': 'Female'}, 
            {'voice_name': 'ash', 'gender': 'Male'},  
            # {'voice_name': 'ballad', 'gender': 'Male'}, 
            {'voice_name': 'coral', 'gender': 'Male'}, 
            {'voice_name': 'echo', 'gender': 'Male'},
            {'voice_name': 'fable', 'gender': 'Female'}, 
            {'voice_name': 'fable', 'gender': 'Male'},
            {'voice_name': 'nova', 'gender': 'Female'}, 
            {'voice_name': 'onyx', 'gender': 'Male'},
            {'voice_name': 'sage', 'gender': 'Female'}, 
            {'voice_name': 'shimmer', 'gender': 'Female'}, 
            # {'voice_name': 'verse', 'gender': 'Female'}, 
            ])

        return all_voices

    def get_voice_names(self, gender=None):
        all_voices = self.get_voices()

        out = set()
        for voice in all_voices:
            if self._gender_filter(voice):
                out.add(voice['voice_name'])

        out = sorted(list(out))

        if out:
            # voice_name = self.config_vars["voice_name"].get()
            # if voice_name not in out:
            #     # our currently selected voice is invalid.  Pick a new one.
            #     self.config_vars["voice_name"].set(out[0])
            return out
        else:
            return []    
    
    def get_tts(self):
        voice = self.override.get('voice_name', self.config_vars["voice_name"].get())
        model = self.override.get('model', self.config_vars["model"].get())

        return ttsOpenAI(
            # api_key=self.api_key, 
            voice=voice,
            model=model,
        )


@dataclass
class ttsOpenAI(voicebox.tts.TTS):
    voice: str = "alloy"
    model: str = "tts-1"
    speed: float = 1.0

    def get_openai_client(self):
        if hasattr(self, 'client'):
            return self.client
        
        if os.path.exists(OPENAI_KEY_FILE):
            with open(OPENAI_KEY_FILE) as h:
                openai_api_key = h.read().strip()

            client = OAI(api_key=openai_api_key)
            self.client = client
            return client
        else:
            log.warning(f"OpenAI Requires valid {OPENAI_KEY_FILE} file")

    def get_speech(self, text: StrOrSSML) -> Audio:
        client = self.get_openai_client()

        log.debug(f"self.voice: {self.voice}")      
        # PCM: Similar to WAV but containing the raw samples in 24kHz (16-bit
        # signed, low-endian), without the header.
        try:
            response = client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                response_format="pcm",
                input=text
            )
        except Exception as e:
            log.error(f"speech.create(model={self.model}, voice={self.voice}, response_format='pcm', input={text})")
            log.error(f"OpenAI TTS speech.create() error: {e}")
            raise

        try:
            samples = np.frombuffer(
                bytes(response.read()),
                dtype=np.int16
            )
        except Exception as e:
            log.error(f"OpenAI TTS PCM->NP error: {e}")
            raise

        try:
            v = voicebox.tts.utils.get_audio_from_samples(
                samples,
                24000
            )
        except Exception as e:
            log.error(f"OpenAI TTS Error converting samples to .wav: {e}")
            raise

        return v

# add this class to the the registry of engines
registry.add_engine(OpenAI)