import configparser
import logging
import os
import tkinter as tk
import webbrowser
from tkinter import ttk

import boto3
import customtkinter as ctk
from voicebox.tts.amazonpolly import AmazonPolly as AmazonPollyTTS

import cnv.database.models as models
import cnv.lib.settings as settings

from .base import MarkdownLabel, TTSEngine

log = logging.getLogger(__name__)

class LinkList(ctk.CTkFrame):
    def __init__(self, parent, links, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.columnconfigure(0, minsize=125, weight=0, uniform="baseconfig")
        self.columnconfigure(1, weight=2, uniform="baseconfig")

        index = 0
        for text, link, docs in links:           
            ctk.CTkButton(
                self,
                text=text,
                command=lambda: webbrowser.open(link)
            ).grid(column=0, row=index)
            
            MarkdownLabel(
                self,
                text=docs,
            ).grid(column=1, row=index)
            index += 1


class AmazonPollyAuthUI(ttk.Frame):
    label = "Amazon Polly"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.credential_fn = os.path.expanduser('~/.aws/credentials')

        mdlabel = MarkdownLabel(
            self,
            text="""[Amazon Polly](https://aws.amazon.com/pm/polly/) is an
            excellent text-to-speech service in AWS. A free tier account is good
            for one year and provides 5 million characters of text-to-speech.
            That is a lot.  After the free year expires, or if you run out it
            (currently) costs $4 per million characters.""".replace("\n", " ")
        ) 
        # mdlabel.on_link_click(self.link_click) 
        
        mdlabel.pack(side="top", fill="x", expand=False)

        #s = ttk.Style()
        #s.configure('EngineAuth.TFrame', background='white')
        #s.configure('EngineAuth.TLabel', background='white')

        # ok, so I'm amused by little things. 
        LinkList(
            self, [
                [
                    'Create an IAM user',
                    "https://docs.aws.amazon.com/IAM/latest/UserGuide/id_users_create.html#id_users_create_console",
                    """You want to create a user with only the permissions that
                    are absolutely necessary.  We're applying the
                    "AmazonPollyReadOnlyAccess" policy.  Nothing else.
                    """
                ],
                [
                    'Create and retrieve the keys',
                    "https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html#Using_CreateAccessKey",
                    """Then we create an access key.  This allows a program to make requests on behalf
                    of the minimal-access user we just created.
                    """
                ]
            ]
            # style="EngineAuth.TFrame"
        ).pack(side="top", fill="both", expand=True)

        auth_settings = ctk.CTkFrame(self)
        # , style='EngineAuth.TFrame')
        auth_settings.columnconfigure(0, minsize=125, weight=0, uniform="baseconfig")
        auth_settings.columnconfigure(1, weight=2, uniform="baseconfig")

        count = 0
        self.tkvars = {}
        for key, text, getter, setter, is_hidden in [(
            'access_key_id',
            'Access Key ID ',
            self.get_access_key_id,
            self.set_access_key_id,
            False
        ), (
            'secret_access_key',
            'Secret Access Key ',
            self.get_secret_access_key,
            self.set_secret_access_key,
            True
        )]:  
            ctk.CTkLabel(
                auth_settings,
                text=text,
                anchor="e",
                # style="EngineAuth.TLabel"
            ).grid(column=0, row=count, sticky='e')
            self.tkvars[key] = tk.StringVar(value=getter())
            self.tkvars[key].trace_add('write', setter)
        
            kwargs = {}
            if is_hidden:
                kwargs['show'] = '*'
                
            entry = ctk.CTkEntry(
                auth_settings,
                textvariable=self.tkvars[key],
                **kwargs                
            )
            # TODO: config show based on is_hidden
            entry.grid(column=1, row=count, sticky='ew')

            count += 1
        auth_settings.pack(side="top", fill="x", expand=True)

    def link_click(self, url):
        # no funny business, just open the URL in a browser.
        webbrowser.open(url, autoraise=True)

    def _read_credentials(self):
        config = configparser.ConfigParser()
        config.read(self.credential_fn)
        return config

    def _set_credential(self, key, cred_key):
        config = self._read_credentials()
        value = self.tkvars[key].get()
        config[cred_key] = value
        with open(self.credential_fn, 'w') as configfile:
            config.write(configfile)

    def get_access_key_id(self):
        config = self._read_credentials()
        return config['default']['aws_access_key_id']
    
    def set_access_key_id(self, *args, **kwargs):
        self._set_credential(
            key="access_key_id",
            cred_key="aws_access_key_id",
        )
        
    def get_secret_access_key(self):
        config = self._read_credentials()
        return config['default']['aws_secret_access_key']
    
    def set_secret_access_key(self, *args, **kwargs):
        self._set_credential(
            key="secret_access_key_id",
            cred_key="aws_secret_access_key",
        )

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
    auth_ui_class = AmazonPollyAuthUI

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
            allowed_language_codes = settings.get_voice_language_codes()
            log.warning(f'No voices exist that support language={allowed_language_codes}/gender={self.gender}.  Ignoring gender.')
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

