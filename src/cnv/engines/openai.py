import logging
import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Union

import numpy as np
import voicebox
from openai import OpenAI as OAI
from voicebox.audio import Audio
from voicebox.types import StrOrSSML

from .base import MarkdownLabel, TTSEngine

log = logging.getLogger(__name__)

OPENAI_KEY_FILE = "openai.key"

class OpenAIAuthUI(ttk.Frame):
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
            "this is a great choice for the most imporant snippets of NPC dialog "
            "where having a few high quality unique voices in reserve pays off."
        )
        mdlabel.pack(side="top", fill="x", expand=False)

        s = ttk.Style()
        s.configure('EngineAuth.TFrame', background='white')
        s.configure('EngineAuth.TLabel', background='white')

        auth_settings = ttk.Frame(self, style='EngineAuth.TFrame')
        auth_settings.columnconfigure(0, minsize=125, weight=0, uniform="baseconfig")
        auth_settings.columnconfigure(1, weight=2, uniform="baseconfig")

        ttk.Label(
            auth_settings,
            text="OpenAI API Key",
            anchor="e",
            style='EngineAuth.TLabel'
        ).grid(column=0, row=0, sticky='e')
        
        self.openai_key = tk.StringVar(value=self.get_openai_key())
        self.openai_key.trace_add('write', self.change_openai_key)
        
        ttk.Entry(
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


def get_openai_client():
    if os.path.exists(OPENAI_KEY_FILE):
        with open(OPENAI_KEY_FILE) as h:
            openai_api_key = h.read().strip()

        client = OAI(api_key=openai_api_key)
        return client
    else:
        log.warning(f"OpenAI Requires valid {OPENAI_KEY_FILE} file")

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
        ('Voice Name', 'voice', "StringVar", "<unconfigured>", {}, "get_voice_names"),
        ('Voice Model', 'model', "StringVar", "<unconfigured>", {}, "get_models"),
        ('Speed', 'speed', "DoubleVar", 1.0, {'min': 0.25, 'max': 4.0, 'resolution': 0.25}, None),
    )

    def get_models(self):
        return [
            'tts-1',
            'tts-1-hd'
        ]

    def get_voice_names(self, gender=None):
        if gender.upper() == "FEMALE":
            return ['alloy', 'nova', 'shimmer', 'fable']
        elif gender.upper() == "MALE":
            return ['echo', 'onyx', 'fable']
        else:
            return [
                'alloy',
                'echo',
                'fable',
                'onyx',
                'nova',
                'shimmer'
            ]
    
    def get_tts(self):
        voice = self.override.get('voice', self.config_vars["voice"].get())
        model = self.override.get('model', self.config_vars["model"].get())

        return ttsOpenAI(
            # api_key=self.api_key, 
            voice=voice,
            model=model,
        )


@dataclass
class ttsOpenAI(voicebox.tts.TTS):
    """    
    """
    voice: Union[str] = "alloy"
    model: Union[str] = "tts-1"
    speed: float = 1.0

    def get_speech(self, text: StrOrSSML) -> Audio:
        client = get_openai_client()

        log.debug(f"self.voice: {self.voice}")      

        # PCM: Similar to WAV but containing the raw samples in 24kHz (16-bit
        # signed, low-endian), without the header.
        response = client.audio.speech.create(
            model=self.model,
            voice=self.voice,
            response_format="pcm",
            input=text
        )

        samples = np.frombuffer(
            bytes(response.read()),
            dtype=np.int16
        )

        return voicebox.tts.utils.get_audio_from_samples(
            samples,
            24000
        )       
