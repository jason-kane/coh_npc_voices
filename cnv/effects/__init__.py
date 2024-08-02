from .base import registry
import glob
import os
import logging

log = logging.getLogger(__name__)

# importing dynamically so we can just drop compatable effects into this
# directory and they can plug themselves in.  Each plugin registers itself and
# provides its own configuration widgets. 

effect_plugins = glob.glob(
    os.path.join(os.path.dirname(__file__), '*.py')
)

for potential in effect_plugins:
    if os.path.isfile(potential):
        module_name = os.path.splitext(os.path.basename(potential))[0]
        if module_name in ['base', '__init__']:
            continue

        full_module_name = "cnv.effects." + module_name
        log.debug(f'Loading {full_module_name} ({potential})')
        __import__(full_module_name, locals(), globals())

log.info(f'* {registry.count()} Effect plugins loaded')
