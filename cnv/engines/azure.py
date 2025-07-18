import json
import logging
import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
import customtkinter as ctk
from typing import Union

import azure.cognitiveservices.speech as speechsdk
import cnv.database.models as models
from cnv.lib import settings
import numpy as np
import voicebox
from voicebox.audio import Audio
from voicebox.types import StrOrSSML

from .base import MarkdownLabel, TTSEngine, registry

log = logging.getLogger(__name__)

AZURE_AUTH_FILE = "azure.json"

class AzureAuthUI(ctk.CTkFrame):
    label = "Azure"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        mdlabel = MarkdownLabel(
            self,
            text="[Azure](https://azure.microsoft.com/en-us/products/ai-services/text-to-speech) "
            "In the azure console you're going to need to create a speech service.  Defaults for "
            "everything not required.  You'll end up in the overview page with two keys and a "
            "region.  We only need one of the keys (and the region).",
            messages_enabled=False
        )
        mdlabel.pack(side="top", fill="x", expand=False)

        auth_settings = ctk.CTkFrame(self)
        auth_settings.columnconfigure(0, minsize=125, weight=0, uniform="baseconfig")
        auth_settings.columnconfigure(1, weight=2, uniform="baseconfig")

        ctk.CTkLabel(
            auth_settings,
            text="Azure Subscription Key",
            anchor="e",
        ).grid(column=0, row=0, sticky='e')
        
        self.azure_subscription_key = tk.StringVar(value=self.get_azure_subscription_key())
        self.azure_subscription_key.trace_add('write', self.change_azure_authentication)
        
        ctk.CTkEntry(
            auth_settings,
            textvariable=self.azure_subscription_key,
            show="*"
        ).grid(column=1, row=0, sticky='ew')
        auth_settings.pack(side="top", fill="x", expand=True)

        ctk.CTkLabel(
            auth_settings,
            text="Azure Region",
            anchor="e",
        ).grid(column=0, row=1, sticky='e')
        
        self.region = tk.StringVar(value=self.get_region())
        self.region.trace_add('write', self.change_azure_authentication)
        
        ctk.CTkEntry(
            auth_settings,
            textvariable=self.region,
        ).grid(column=1, row=1, sticky='ew')
        auth_settings.pack(side="top", fill="x", expand=True)

    def change_azure_authentication(self, a, b, c):
        with open(AZURE_AUTH_FILE, 'w') as h:
            h.write(
                json.dumps({
                    'subscription_key': self.azure_subscription_key.get(),
                    'service_region': self.region.get()
                })
            )

    def get_azure_authentication(self, key):
        if os.path.exists(AZURE_AUTH_FILE):
            with open(AZURE_AUTH_FILE, 'r') as h:
                value = json.loads(h.read())
        
            return value[key]
        else:
            return ""

    def get_azure_subscription_key(self):
        return self.get_azure_authentication('subscription_key')

    def get_region(self):
        return self.get_azure_authentication('service_region')


def get_azure_config():
    if os.path.exists(AZURE_AUTH_FILE):
        with open(AZURE_AUTH_FILE) as h:
            config = json.loads(h.read())

        speech_key = config['subscription_key']
        service_region = config['service_region']

        client = speechsdk.SpeechConfig(
            subscription=speech_key,
            region=service_region
        )
        return client
    else:
        log.warning(f"Azure Requires valid {AZURE_AUTH_FILE} file")


class Azure(TTSEngine):
    """
    """
    cosmetic = "Azure"
    key = "azure"
    auth_ui_class = AzureAuthUI

    config = (
        ('Voice Name', 'voice', "StringVar", "<unconfigured>", {}, "get_voice_names"),
    )

    def get_models(self):
        return [
            'tts-1',
            'tts-1-hd'
        ]

    def get_voice_names(self, gender=None):
        voices = self.get_voices()
        allow_language_codes = settings.get_voice_language_codes()

        language_filtered = []
        for v in voices:
            if v['locale'].split("-")[0] not in allow_language_codes:
                continue
            language_filtered.append(v)

        # getting the wrong gender (because the right one isn't available)
        # isn't as bad as a voice that can't pronounce the language.
        gender_filtered = []
        if gender:
            for v in language_filtered:
                if gender is None or v['gender'] != gender:
                    continue
                gender_filtered.add(v)

        if gender_filtered:        
            return [v['voice'] for v in gender_filtered]
        else:
            return [v['voice'] for v in language_filtered]

    def get_voices(self):
        all_voices = models.diskcache(f'{self.key}_voice')

        if all_voices is None:
            speech_config = get_azure_config()

            speech_synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=speech_config,
                audio_config=None
            )
            
            # Request the list of available voices
            result = speech_synthesizer.get_voices_async().get()

            all_voices = []
            for entry in result.voices:
                # log.info(f"{entry.gender.name=} {dir(entry.gender)}")

                all_voices.append({
                    'voice': entry.short_name,
                    'gender': entry.gender.name,
                    'locale': entry.locale
                })

            models.diskcache(f'{self.key}_voice', all_voices)

        return all_voices
   
    def get_tts(self):
        voice = self.override.get('voice', self.config_vars["voice"].get())

        return ttsOpenAI(
            voice=voice,
        )


@dataclass
class ttsOpenAI(voicebox.tts.TTS):
    """    
    """
    voice: Union[str] = "en-US-AvaMultilingualNeural"

    def get_speech(self, text: StrOrSSML) -> Audio:
        speech_config = get_azure_config()

        log.debug(f"self.voice: {self.voice}")

        speech_config.speech_synthesis_voice_name = self.voice
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat['Riff24Khz16BitMonoPcm']
        )

        speech_synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=None
        )

        result = speech_synthesizer.speak_text(text)

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:   
            stream = speechsdk.AudioDataStream(result)
            
            audio_buffer = bytes(10000000)
            size = stream.read_data(audio_buffer)

            log.debug('Creating numpy buffer')
            samples = np.frombuffer(
                audio_buffer[:size],
                dtype=np.int16
            )

            return voicebox.tts.utils.get_audio_from_samples(
                samples,
                24000
            )

# add this class to the the registry of engines
registry.add_engine(Azure)