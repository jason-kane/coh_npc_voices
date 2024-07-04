
import logging

import boto3
import cnv.database.models as models
import cnv.lib.settings as settings
from voicebox.tts.amazonpolly import AmazonPolly as AmazonPollyTTS

from .base import TTSEngine

log = logging.getLogger(__name__)

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

