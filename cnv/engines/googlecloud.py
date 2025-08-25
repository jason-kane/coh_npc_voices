import logging
import os
import random
import webbrowser

import customtkinter as ctk
import voicebox
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.cloud import texttospeech
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from sqlalchemy import select

import cnv.database.models as models
import cnv.lib.settings as settings

from .base import MarkdownLabel, TTSEngine, registry


log = logging.getLogger(__name__)

# pitch control was removed by google?
with_pitch = False

# https://cloud.google.com/text-to-speech/docs/reference/rest/v1/text/synthesize
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

# the credentials are a secret in a typical oauth workflow but we are a desktop
# applicaton, there are no secrets.
#
# google auth uses this "secret" as a unique to identify our application.  It
# pops open a browser, asks about auth to give the application permission to
# utilize the users google account for text-to-speech.
# 
# The response is a 'code', which is sent to this application. the code is then
# sent back to google to create a token. that token can be used on every
# text-to-speech request until it expires, then we refresh it to get a new
# token.  The oauth library does all the heavy lifting.
#
# To completely remove access, delete the _token_.  If you delete the credential
# you will have to re-install.
credential_file = "google_credential.json"
token_file = "google_token.json"

# it looks like I have some hoops to jump through before google will let this be
# a "published" app for oauth purposes. nothing huge.  I need a domain with a
# few pages, a youtube explaining what I'm doing, a written explanation of what
# I'm doing and verified domains.  That seems overwhelming, but it isn't really
# that bad but it will take some time.  In the meantime this is in "test" mode;
# the 100 user limit is no big deal but it's unclear to me if they need to be
# pre-approved.  If they do this will not work and I'm sorry, that kind of
# sucks.  If you send me your google account email address I can add you to the
# test user list.
#
# Since I'm not really sure oauth will work smoothly; I'll have ADC as an
# alternative.  That is Applicaton Default Credentials; it means creating a json
# file that is essentially a username/password for your google cloud account.
# You decide exactly what it has permission to do so it isn't as insecure as it
# sounds.

def get_credentials():
    """
    Returns credentials or None.  Does not make the user do anything.
    This is what anything that needs google access calls to retrieve
    the credentials.
    """
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(
            token_file, SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # try and refresh the credential
            try:
                creds.refresh(Request())

                # persist the refreshed token to disk
                with open(token_file, "w") as token:
                    token.write(creds.to_json())

            except RefreshError as err:
                # our token can't be refreshed.
                log.error(err)
                os.unlink(token_file)
                creds = None
        else:
            creds = None

    if creds is None and 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
        # https://cloud.google.com/docs/authentication/provide-credentials-adc#local-key
        # https://cloud.google.com/docs/authentication/external/set-up-adc
        log.debug('Using Application Default Credential: %s', os.environ['GOOGLE_APPLICATION_CREDENTIALS'])
        return None
    else:
        log.debug('Using:  gcloud auth application-default')
        log.debug('If it does not work, try "gcloud auth application-default login"')

    return creds


class GoogleCloudAuthUI(ctk.CTkFrame):
    label = "Google Cloud"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.columnconfigure(0, weight=1)

        mdlabel = MarkdownLabel(
            self,
            text="""[Google Text-to-Speech](https://cloud.google.com/text-to-speech?hl=en)
            is an solid txt-to-speech service from google. A free tier account
            (currently 7/24) provides 1 million characters per month. if you run
            out it (currently) costs $4-$16 per million characters, billed
            per-character.
            """.replace("\n", " "),
            messages_enabled=False
        ) 
        # mdlabel.on_link_click(self.link_click) 
        
        mdlabel.grid(column=0, row=0, sticky="nsew")
        #pack(side="top", fill="x", expand=False)
        #s = ttk.Style()
        #s.configure('EngineAuth.TFrame', background='white')
        #s.configure('EngineAuth.TLabel', background='white')

        frame = ctk.CTkFrame(self)

        frame.columnconfigure(0, weight=2)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=2)

        ctk.CTkButton(
            frame,
            text="Browser oauth2 authentication",
            command=self.authenticate
        ).grid(column=0, row=0)

        ctk.CTkLabel(
            frame,
            font=ctk.CTkFont(
                size=12,
                weight="bold",
                slant='italic'
            ),
            text=" OR ",
            anchor="center",
            # style="EngineAuth.TLabel"
        ).grid(column=1, row=0, sticky="nsew")

        adc = ctk.CTkFrame(frame)
        ctk.CTkButton(
            adc,
            text="Create a service account key",
            command=lambda: self.link_click('https://cloud.google.com/iam/docs/keys-create-delete#creating')
        ).pack(side="top", fill='x')

        ctk.CTkButton(
            adc,
            text="Set GOOGLE_APPLICATION_CREDENTIALS",
            command=lambda: self.link_click('https://cloud.google.com/docs/authentication/provide-credentials-adc#local-key')
        ).pack(side="top", fill='x')
        adc.grid(column=2, row=0, sticky="n")

        frame.grid(column=0, row=1, sticky="nsew")

    def link_click(self, url):
        log.info('link click')
        # no funny business, just open the URL in a browser.
        webbrowser.open(url, autoraise=True)

    def authenticate(self):
        if not os.path.exists(credential_file):
            log.error(f'Installation error:  Required file {credential_file} not found.')
            return

        flow = InstalledAppFlow.from_client_secrets_file(
            credential_file, SCOPES
        )
        creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(token_file, "w") as token:
            token.write(creds.to_json())


class GoogleCloud(TTSEngine):
    """
    TODO: This engine needs some help.  The problem is that there are just too many voices.  We can't just use one select box, we have to narrow it down more.
    """
    cosmetic = "Google Text-to-Speech"
    key = 'googletts'
    auth_ui_class = GoogleCloudAuthUI

    config = (
        ('Voice Name', 'voice_name', "StringVar", "<unconfigured>", {}, "get_voice_names"),
        ('Speaking Rate', 'speaking_rate', "DoubleVar", 1, {'min': 0.75, 'max': 1.25, 'digits': 3, 'resolution': 0.25}, None)
        # ('Voice Pitch', 'voice_pitch', "DoubleVar", 1, {'min': -10, 'max': 10, 'resolution': 0.5}, None)
    )   

    def _language_code_filter(self, voice):
        """
        True if this voice is able to speak this language_code.
        """
        allowed_language_codes = settings.get_voice_language_codes()
        #log.info(f"{allowed_language_codes=}")

        # two letter code ala: en, and matches against en-whatever
        for allowed_code in allowed_language_codes:
            if any(f"{allowed_code}-" in code for code in voice["language_codes"]):
                log.debug(f'{allowed_code=} matches with {voice["language_codes"]=}')
                return True
        return False

    def get_voice_names(self, gender=None):
        log.debug(f'get_voices_names({gender=})')
        all_voices = self.get_voices()

        if gender and not hasattr(self, 'gender'):
            self.gender = gender
        
        out = set()
        for voice in all_voices:
            #log.info(f'considering {voice=} to be added to {out=}')
            if self._language_code_filter(voice):
                if self._gender_filter(voice):
                    out.add(voice['voice_name'])
        
        if not out:
            # seems pretty unlikely, but..
            log.error(f'There are no voices available for the language: {settings.get_voice_language_codes()} and gender={self.gender.title()}')
            for voice in all_voices:
                # try without the gender filter -- interesting choice I guess;
                # if you have to drop language or gender, which is a worse
                # customer experience?  Misgender or Bad accent?  That is the
                # choice here.
                #
                # not really, in practice getting the language wrong is way
                # worse, because it's frequenctly unintelligible.  it is a cool
                # character effect, it's wrong to call this 'accent', it's more
                # like what would X sound like if someone that only speeks Y tried to read
                # it.   Situational at best.

                # misgender:
                if self._language_code_filter(voice):
                    out.add(voice['voice_name'])

                # or bad accent:
                #if self._gender_filter(voice):
                #    out.add(voice['voice_name'])
        
        out = sorted(list(out))

        if out:
            # voice_name = self.config_vars["voice_name"].get()
            # if voice_name not in out:
            #     # our currently selected voice is invalid.  Pick a new one.
            #     log.error(f'Voice {voice_name} expected in {out}')
            #     raise InvalidVoiceException()
                
                # random_voice = random.choice(out)
                # log.error(f', replacing with {random_voice}.')
                # self.config_vars["voice_name"].set(random_voice)
            return out
        else:
            return []

    def get_voices(self):
        all_voices = models.diskcache(f'{self.key}_voice_name', force=False)

        if all_voices is None:
            log.warning('Google get_voices() Cache Miss')
            client = texttospeech.TextToSpeechClient()
            req = texttospeech.ListVoicesRequest()
            resp = client.list_voices(req)
            all_voices = []
            for voice in resp.voices:
                # log.info(f'{voice.language_codes=}')
                # log.info(dir(voice.language_codes))
                log.debug(f"{voice.ssml_gender=}")

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
        if with_pitch:
            voice_pitch = self.override.get('voice_pitch', self.config_vars["voice_pitch"].get())
        language_code = self.get_voice_language(voice_name)

        kwargs = {}
        credentials = get_credentials()
        if credentials:
            kwargs['credentials'] = credentials

        client = texttospeech.TextToSpeechClient(
            **kwargs
        )

        audio_config = texttospeech.AudioConfig(
            speaking_rate=float(speaking_rate), 
            # pitch=float(voice_pitch)
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

# add this class to the the registry of engines
registry.add_engine(GoogleCloud)
