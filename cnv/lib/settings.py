import logging
import inspect
import json
import os
import hashlib
import re

LOGLEVEL = logging.INFO
# this is the ultimate fallback engine if there is nothing configured
DEFAULT_ENGINE = "Windows TTS"
DEFAULT_NORMALIZE = False

PRESETS = "presets.json"
ALIASES = "aliases.json"

# want to include a new language?  
# It needs to be supported by https://mymemory.translated.net/ And whatever TTS
# engine you want to use 
#
#   https://cloud.google.com/text-to-speech/docs/voices
#   https://docs.aws.amazon.com/polly/latest/dg/supported-languages.html
#
#  If it satisfies those two requirements.. add it to this list. that is all it
#  takes.
#
# (translation, (voice)) any voice that has any of the the indicated prefixes
# are considered acceptable
# 
LANGUAGES = {
    "Chinese": ("zh", ("cmn", )),  # simplified
    "English": ("en", ("en", )),
    "French": ("fr", ("fr", )),
    "German": ("de", ("de", )),
    "Japanese": ("ja", ("ja", )),
    "Korean": ("ko", ("ko", )),
    "Spanish": ("es", ("es", ))
}

REPLAY = False
XP_IN_REPLAY = False
SPEECH_IN_REPLAY = False
SESSION_CLEAR_IN_REPLAY = False

log = logging.getLogger(__name__)


def clip_library_dir() -> str:
    return get_config_key('clip_library_dir')


def log_dir() -> str:
    return get_config_key('logdir')


def how_did_i_get_here():
    log.info(
        "| Called by: \n%s", "\n".join([str(frame) for frame in inspect.stack()[1:]])
    )


CACHE_CONFIG = {}
CACHE_CONFIG_MTIME = {}


def get_config(cf="config.json"):
    global CACHE_CONFIG
    global CACHE_CONFIG_MTIME

    if os.path.exists(cf):
        mtime = os.path.getmtime(cf)
        if CACHE_CONFIG_MTIME.get(cf) is None or mtime != CACHE_CONFIG_MTIME[cf]:
            with open(cf) as h:
                try:
                    config = json.loads(h.read())
                except json.decoder.JSONDecodeError:
                    log.error("Invalid json in %s", cf)
                    config = {}

                CACHE_CONFIG[cf] = config
                CACHE_CONFIG_MTIME[cf] = mtime

    if cf in CACHE_CONFIG:
        return CACHE_CONFIG[cf]
    else:
        config = {}
    return config


def set_config_key(key, value, cf="config.json"):
    config = get_config(cf=cf)
    config[key] = value
    save_config(config, cf=cf)


def save_config(config, cf="config.json"):
    global CACHE_CONFIG
    global CACHE_CONFIG_MTIME
    with open(cf, "w") as h:
        h.write(json.dumps(config, indent=4, sort_keys=True))
        CACHE_CONFIG[cf] = config
        CACHE_CONFIG_MTIME[cf] = os.path.getmtime(cf)


def get_config_key(key, default=None, cf="config.json") -> str | None:
    config = get_config(cf=cf)
    return config.get(key, default)


def taggify(instr):
    tag = instr.replace(' ', '')
    return tag[:10] + "_" + hashlib.sha256(tag.encode('utf8')).hexdigest()[:4]


def set_toggle(key, value):
    set_config_key(
        key=f'toggle_{key}',
        value=value
    )

def get_toggle(key):
    return get_config_key(
        key=f'toggle_{key}'
    ) == "on"


def get_alias(group):
    return get_config_key(key=group, default=group, cf="aliases.json")


def get_preset(group):
    return get_config_key(key=group, default={}, cf="presets.json")


def get_language_code():
    """
    Returns the two character language code for feeding the translator
    """
    language = get_config_key('language', default="English")
    if language:
        return LANGUAGES[language][0]
    else:
        return None

def get_language_code_regex():
    code = get_language_code()
    return f"{code}-.*"

def get_voice_language_codes():
    """
    Returns a list of language codes that would be acceptable for allow-list
    filtering voices in any engine.
    """
    language = get_config_key('language', default="English")
    if language:
        return LANGUAGES[language][1]  
    else:
        return None


CACHE_DIR = "cache"


def clean_customer_name(in_name):
    if in_name:
        clean_name = re.sub(r'[^\w]', '', in_name)
    else:
        clean_name = "GREAT_NAMELESS_ONE"

    if in_name is None:
        in_name = "GREAT NAMELESS ONE"

    return in_name, clean_name


def cache_filename(name, message, rank):
    clean_message = re.sub(r'[^\w]', '', message)
    clean_message = hashlib.sha256(message.encode()).hexdigest()[:5] + f"_{clean_message[:10]}"
    clean_message += rank[0]
    return clean_message


def get_cachefile(name, message, category, rank):
    name, clean_name = clean_customer_name(name)
    log.debug(f"{name=} {clean_name=} {message=} {rank=}")

    # ie: abcde_timetodan.mp3
    # this should be unique to this messags, it's only
    # a 5 character hash, collisions are possible.
    filename = cache_filename(name, message, rank)

    # do we already have this NPC/Message rendered to an audio file?
    # first we need the path the file ought to have
    try:
        cachefile = os.path.abspath(
            os.path.join(clip_library_dir(), category, clean_name, filename)
        )
    except Exception:
        log.error(
            f'invalid os.path.join("clip_library", {category}, {clean_name}, {filename})'
        )
        raise

    return cachefile

def diskcache(key, value=None):
    """
    key must be valid as a base filename
    value must be None or a json-able object
    """
    log.debug(f"diskcache({key=}, {value=})")
    filename = os.path.join(CACHE_DIR, key + ".json")
    if value is None:
        if os.path.exists(filename):
            with open(filename, "rb") as h:
                content = json.loads(h.read())
            return content
    else:
        if not os.path.exists(CACHE_DIR):
            os.mkdir(CACHE_DIR)

        with open(filename, "w") as h:
            h.write(json.dumps(value, indent=2))

        return value


ALL_NPC = {}
ALL_NPC_FN = os.path.join(
    os.path.dirname(__file__), 
    "..", '..',
    "all_npcs.json"
)

def get_npc_data(character_name):
    global ALL_NPC
    log.debug(f"get_npc_data({character_name=})")
    if not ALL_NPC:
        # log.info(os.listdir(
        #     os.path.dirname(ALL_NPC_FN)
        # ))

        with open(ALL_NPC_FN, "r") as h:
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
