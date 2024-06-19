import logging
import inspect
import sys
import json
import os

LOGLEVEL=logging.INFO 
# this is the ultimate fallback engine if there is nothing configured
DEFAULT_ENGINE="Windows TTS"
DEFAULT_NORMALIZE=False

PRESETS = "presets.json"
ALIASES = "aliases.json"

# by default, don't save things players say.  It's not likely
# to cache hit anyway.  
PERSIST_PLAYER_CHAT = True

REPLAY=False

logging.basicConfig(
    level=LOGLEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger(__name__)

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
        h.write(json.dumps(config, indent=4, sort_keys=True))
        CACHE_CONFIG = config

def get_config_key(key, default=None):
    config = get_config()
    return config.get(key, default)

ALL_NPC = {}
def get_npc_data(character_name):
    global ALL_NPC
    log.info(f'get_npc_data({character_name=})')
    if not ALL_NPC:
        with open("all_npcs.json", "r") as h:
            ALL_NPC = json.loads(h.read())
    return ALL_NPC.get(character_name)

def get_npc_gender(character_name):
    # what is this characters gender (if it has one)?
    npc_data = get_npc_data(character_name)
    gender = None
    if npc_data:
        if npc_data["gender"] == "GENDER_MALE":
            gender = "Male"
        elif npc_data["gender"] == "GENDER_FEMALE":
            gender = "Female"
    
    # Neuter == None
    return gender