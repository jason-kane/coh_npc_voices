from .base import registry
import glob
import os
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


# importing dynamically so we can just drop compatable engine configurations
# into this directory and they just plug themselves in.  Each plugin registers
# itself and provides its own configuration widgets. 

engine_path = os.path.join(os.path.dirname(__file__), '*.py')

log.info(f'Loading TTS Engines... [{engine_path}]')
tts_engines = glob.glob(
    engine_path
)

for potential in tts_engines:
    # log.debug(f'Checking {potential} for TTS Engines...')
    if os.path.isfile(potential):
        module_name = os.path.splitext(os.path.basename(potential))[0]
        if module_name in ['base', '__init__']:
            continue

        full_module_name = "cnv.engines." + module_name
        log.info(f'Loading {full_module_name}')
        __import__(full_module_name, locals(), globals())

log.info(f'* {registry.count()} TTS Engines loaded')
