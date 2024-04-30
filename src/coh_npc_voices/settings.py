import logging
import inspect
import sys
import json
import os

LOGLEVEL=logging.INFO 
# this is the ultimate fallback engine if there is nothing configured
DEFAULT_ENGINE="Windows TTS"

PRESETS = "presets.json"
ALIASES = "aliases.json"

# by default, don't save things players say.  It's not likely
# to cache hit anyway.  
PERSIST_PLAYER_CHAT = False

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

CACHE_CONFIG = {}

def get_config():
    global CACHE_CONFIG
    if CACHE_CONFIG:
        return CACHE_CONFIG
    
    if os.path.exists('config.json'):
        with open('config.json') as h:
            config = json.loads(h.read())
            CACHE_CONFIG = config
    else:
        config = {}
    return config

def set_config_key(key, value):
    config = get_config()
    config[key] = value
    save_config(config)

def save_config(config):
    global CACHE_CONFIG
    with open('config.json', 'w') as h:
        h.write(json.dumps(config))
        CACHE_CONFIG = config

def get_config_key(key, default=None):
    config = get_config()
    return config.get(key, default)

ALL_NPC = {}
def get_npc_data(character_name):
    global ALL_NPC
    if not ALL_NPC:
        with open("all_npcs.json", "r") as h:
            ALL_NPC = json.loads(h.read())
    return ALL_NPC.get(character_name)