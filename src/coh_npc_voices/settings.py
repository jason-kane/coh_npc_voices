import logging
import inspect
import sys

LOGLEVEL=logging.INFO 
DEFAULT_ENGINE="Windows TTS"

PRESETS = "presets.json"
ALIASES = "aliases.json"

logging.basicConfig(
    level=LOGLEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("__name__")

def how_did_i_get_here():
    log.info(
        '| Called by: \n%s', 
        '\n'.join([str(frame) for frame in inspect.stack()[1:]])
    )    