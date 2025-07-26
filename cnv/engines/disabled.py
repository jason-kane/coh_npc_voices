import logging
from .base import TTSEngine, registry

log = logging.getLogger(__name__)


class Disabled(TTSEngine):
    """
    Disabled engine.
    """
    cosmetic = "Disabled"
    key = "disabled"
    api_key = None
    auth_ui_class = None
    config = []

    def say(self, message, effects, sink, *args, **kwargs):
        return

# add this class to the the registry of engines
registry.add_engine(Disabled)