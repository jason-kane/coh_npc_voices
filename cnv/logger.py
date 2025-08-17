from rich.logging import RichHandler
from logging.handlers import QueueHandler
from logging.config import dictConfig

from logging.handlers import QueueListener

class AutoStartLogQueueListener(QueueListener):

    def __init__(self, queue, *handlers, respect_handler_level=False):
        super().__init__(queue, *handlers, respect_handler_level=respect_handler_level)
        # Start the listener immediately.
        self.start()


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
                #'class': QueueHandler
                'class': RichHandler,
            },
            'error_file': {
                'level': 'ERROR',
                'formatter': 'logfile',
                'class': 'logging.FileHandler',
                'filename': 'error.log',
                'mode': 'a'
            },
            'log_viewer': {
                'level': 'DEBUG',
                'formatter': 'standard',
                'class': QueueHandler,
                'listener': AutoStartLogQueueListener,
                'queue': {
                    "()": 'queue.Queue',
                    'maxsize': 100
                }
            },
        },
        'loggers': { 
            '': {  # root logger
                'handlers': ['default', 'error_file', 'log_viewer'],
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
