import logging
import os
import tempfile
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Union

import customtkinter as ctk
import elevenlabs
import voicebox
from elevenlabs.client import ElevenLabs as ELABS
from voicebox.audio import Audio
from voicebox.types import StrOrSSML

import cnv.database.models as models
import cnv.lib.audio as audio

from .base import MarkdownLabel, TTSEngine, registry

log = logging.getLogger(__name__)

class ElevenLabsAuthUI(ctk.CTkFrame):
    label = "ElevenLabs"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        mdlabel = MarkdownLabel(
            self,
            text="[ElevenLabs](https://elevenlabs.io/) is a leading edge company focused on providing "            
            "top quality text to speech technology.  A free account provides 10,000 characters "
            "of text-to-speech.  When it runs out we can automatically toggle over to your "
            "secondary voice provider.  Don't like the drop in quality?  Elevenlabs "
            "[pricing](https://elevenlabs.io/pricing) is premium but not unreasonable.\n"
            "Supporting using your voice clone as your own playback voice "
            "is surpisingly close to easy.\n"
            "* Create an account\n"
            "* login to it\n"
            "* In the bottom left corner, click yourself\n"
            "* Choose *'Profile + API key'*",
        )
        mdlabel.pack(side="top", fill="x", expand=False)

        auth_settings = ctk.CTkFrame(self)
        auth_settings.columnconfigure(0, minsize=125, weight=0, uniform="baseconfig")
        auth_settings.columnconfigure(1, weight=2, uniform="baseconfig")

        ctk.CTkLabel(
            auth_settings,
            text="ElevenLabs API Key",
            anchor="e",
            # style='EngineAuth.TLabel'
        ).grid(column=0, row=0, sticky='e')
        
        self.elevenlabs_key = tk.StringVar(value=self.get_elevenlabs_key())
        self.elevenlabs_key.trace_add('write', self.change_elevenlabs_key)
        ctk.CTkEntry(
            auth_settings,
            textvariable=self.elevenlabs_key,
            show="*"
        ).grid(column=1, row=0, sticky='ew')
        auth_settings.pack(side="top", fill="x", expand=True)

    def change_elevenlabs_key(self, a, b, c):
        with open("eleven_labs.key", 'w') as h:
            h.write(self.elevenlabs_key.get())

    def get_elevenlabs_key(self):
        keyfile = 'eleven_labs.key'
        value = None

        if os.path.exists(keyfile):
            with open(keyfile, 'r') as h:
                value = h.read()
        return value


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


class ElevenLabs(TTSEngine):
    """
    Elevenlabs detects the incoming language; so in theory every voice works with every language.  I have doubts.
    """
    cosmetic = "Eleven Labs"
    key = "elevenlabs"
    api_key = None
    auth_ui_class = ElevenLabsAuthUI

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
        for voice in models.diskcache('elevenlabs_voice_name'):
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

# add this class to the the registry of engines
registry.add_engine(ElevenLabs)