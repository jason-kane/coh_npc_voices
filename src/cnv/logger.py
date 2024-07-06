from rich.logging import RichHandler
from logging.config import dictConfig

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
            'level': 'INFO',
            'formatter': 'standard',
            'class': RichHandler
        },
        'error_file': { 
            'level': 'ERROR',
            'formatter': 'logfile',
            'class': 'logging.FileHandler',
            'filename': 'error.log',
            'mode': 'a'
        },
    },
    'loggers': { 
        '': {  # root logger
            'handlers': ['default', 'error_file'],
            'level': 'DEBUG',
            'propagate': True
        },
        "botocore.credentials": {
            'handlers': ['default', 'error_file'],
            'level': 'WARNING',
            'propagate': True            
        }
        # 'coh_npc_voices': {
        #     'handlers': ['default', 'error_file'],
        #     'level': 'DEBUG',
        #     'propagate': True
        # },
    } 
}

def init():
    dictConfig(LOGGING_CONFIG)
