from rich.logging import RichHandler
from rich.console import Console
from logging.config import dictConfig

# richHandler = RichHandler(console=Console(width=256))

LOGGING_CONFIG = { 
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': { 
        'standard': {
            'format': '%(message)s'
        },
        'logfile': {
            'format': '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s'
        }
    },
    'handlers': { 
        'default': { 
            'level': 'DEBUG',
            'formatter': 'standard',
            'class': RichHandler,
            #"console": Console(width=256)
        },
        'error_file': { 
            'level': 'INFO',
            'formatter': 'logfile',
            'class': 'logging.FileHandler',
            'filename': 'error.log',
            'mode': 'a'
        },
    },
    'loggers': { 
        '': {  # root logger
            'handlers': ['default', 'error_file'],
            'level': 'INFO',
            'propagate': False
        },
        "botocore.credentials": {
            'handlers': ['default', 'error_file'],
            'level': 'WARNING',
            'propagate': True           
        },
        'cnv.voices.voice_editor': {
            'handlers': ['default', ],
            'level': 'INFO',
            'propagate': False
        },
        'cnv.chatlog.npc_chatter': {
            'handlers': ['default', ],
            'level': 'INFO',
            'propagate': False
        },
        'cnv.engines.base': {
            'handlers': ['default', ],
            'level': 'INFO',
            'propagate': False
        },
        'cnv.effects.effects': {
            'handlers': ['default', ],
            'level': 'INFO',
            'propagate': False
        },
    } 
}

def init():
    dictConfig(LOGGING_CONFIG)
