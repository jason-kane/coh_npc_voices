from rich.logging import RichHandler
from logging.config import dictConfig

def init(DEBUG=False):
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
                'level': 'DEBUG' if DEBUG else 'INFO',
                'formatter': 'standard',
                'class': RichHandler,
            },
            'error_file': { 
                'level': 'DEBUG' if DEBUG else 'INFO',
                'formatter': 'logfile',
                'class': 'logging.FileHandler',
                'filename': 'error.log',
                'mode': 'a'
            },
        },
        'loggers': { 
            '': {  # root logger
                'handlers': ['default', 'error_file'],
                'level': 'DEBUG' if DEBUG else 'INFO',
                'propagate': False
            },
            "botocore.credentials": {
                'handlers': ['default', 'error_file'],
                'level': 'WARNING',
                'propagate': True           
            },
            'matplotlib.font_manager': {
                'handlers': ['default', ],
                'level': 'INFO',  # debug is super noisy and not very helpful
                'propagate': False
            },
            'tkinterweb_tkhtml': {
                'handlers': ['default', ],
                'level': 'INFO',  # debug is super noisy and not very helpful
                'propagate': False
            },
            'cnv.voices.voice_editor': {
                'handlers': ['default', ],
                'level': 'DEBUG' if DEBUG else 'INFO',
                'propagate': False
            },
            'cnv.chatlog.npc_chatter': {
                'handlers': ['default', ],
                'level': 'DEBUG' if DEBUG else 'INFO',
                'propagate': False
            },
            'cnv.engines.base': {
                'handlers': ['default', ],
                'level': 'DEBUG' if DEBUG else 'INFO',
                'propagate': False
            },
            'cnv.engines.windowstts': {
                'handlers': ['default', ],
                'level': 'DEBUG' if DEBUG else 'INFO',
                'propagate': False
            },        
            'cnv.effects.effects': {
                'handlers': ['default', ],
                'level': 'DEBUG' if DEBUG else 'INFO',
                'propagate': False
            },
            'cnv.effects.ringmod': {
                'handlers': ['default', ],
                'level': 'DEBUG' if DEBUG else 'INFO',
                'propagate': False
            },        
            'cnv.effects.base': {
                'handlers': ['default', ],
                'level': 'DEBUG' if DEBUG else 'INFO',
                'propagate': False
            },
        } 
    }

    dictConfig(LOGGING_CONFIG)
