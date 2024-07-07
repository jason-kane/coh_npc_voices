import logging

from .amazonpolly import AmazonPolly
from .base import USE_SECONDARY
from .elevenlabs import ElevenLabs
from .googlecloud import GoogleCloud
from .openai import OpenAI
from .windowstts import WindowsTTS

log = logging.getLogger(__name__)



# https://github.com/coqui-ai/tts 
#
# I tried this.  Doesn't work yet in Windown w/Py 3.12 due to the absense of
# compiled pytorch binaries.  I'm more than a little worried the resources
# requirment and speed will make it impractical.

def get_engine(engine_name):
    for engine_cls in ENGINE_LIST:
        if engine_name == engine_cls.cosmetic:
            log.debug(f"found {engine_cls.cosmetic}")
            return engine_cls


ENGINE_LIST = [ 
    WindowsTTS, 
    GoogleCloud, 
    ElevenLabs, 
    AmazonPolly, 
    OpenAI,
]
