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

def get_config(cf="config.json"):
    global CACHE_CONFIG
    if cf in CACHE_CONFIG:
        return CACHE_CONFIG[cf]
    
    if os.path.exists(cf):
        with open(cf) as h:
            config = json.loads(h.read())
            CACHE_CONFIG[cf] = config
    else:
        config = {}
    return config

def set_config_key(key, value, cf="config.json"):
    config = get_config(cf=cf)
    config[key] = value
    save_config(config, cf=cf)

def save_config(config, cf="config.json"):
    global CACHE_CONFIG
    with open(cf, 'w') as h:
        h.write(json.dumps(config, indent=4, sort_keys=True))
        CACHE_CONFIG[cf] = config

def get_config_key(key, default=None, cf="config.json"):
    config = get_config(cf=cf)
    return config.get(key, default)

def get_alias(group):
    return get_config_key(
        key=group, 
        default=group,
        cf="aliases.json"
    )

def get_preset(group):
    return get_config_key(
        key=group, 
        default={},
        cf="presets.json"
    )    

CACHE_DIR = 'cache'
def diskcache(key, value=None):
    """
    key must be valid as a base filename
    value must be None or a json-able object
    """
    log.debug(f'diskcache({key=}, {value=})')
    filename = os.path.join(CACHE_DIR, key + ".json")
    if value is None:
        if os.path.exists(filename):
            with open(filename, 'rb') as h:
                content =json.loads(h.read())
            return content
    else:
        if not os.path.exists(CACHE_DIR):
            os.mkdir(CACHE_DIR)

        with open(filename, 'w') as h:
            h.write(json.dumps(value, indent=2))
        
        return value

ALL_NPC = {}
def get_npc_data(character_name):
    global ALL_NPC
    log.debug(f'get_npc_data({character_name=})')
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