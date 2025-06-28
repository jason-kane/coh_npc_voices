import logging
from dataclasses import dataclass

import cnv.database.models as models
import cnv.lib.settings as settings
import numpy as np
import tts.sapi
import voicebox
from voicebox.audio import Audio
from voicebox.types import StrOrSSML

from .base import TTSEngine, registry

log = logging.getLogger(__name__)


class WindowsTTS(TTSEngine):
    cosmetic = "Windows TTS"
    key = "windowstts"
    auth_ui_class = None

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


@dataclass
class WindowsSapi(voicebox.tts.TTS):
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

        # hijack it, write to our memory stream
        voice.voice.AudioOutputStream = stream

        # speak the text
        voice.say(text)

        # restore our stream hijack
        voice.voice.AudioOutputStream = temp_stream
        
        samples = np.frombuffer(
            bytes(stream.GetData()), 
            dtype=np.int16
        )

        # voicebox == numpy, I don't see any way around it in general. in this
        # case we could switch to an SpFileStream and dump a .wav then make this
        # get_audio_from_wav_file, but it's just np there vs np here.
        audio = voicebox.tts.utils.get_audio_from_samples(
            samples,
            22050
        )

        return audio
    
# add this class to the the registry of engines
registry.add_engine(WindowsTTS)