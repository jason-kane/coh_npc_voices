import logging

import cnv.database.models as models
import cnv.lib.settings as settings
import voicebox
from google.cloud import texttospeech
from sqlalchemy import select

from .base import TTSEngine

log = logging.getLogger(__name__)

class GoogleCloud(TTSEngine):
    cosmetic = "Google Text-to-Speech"
    key = 'googletts'
    auth_ui_class = None

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

