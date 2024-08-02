import logging

import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LBoolean,
    LScale,
)

log = logging.getLogger(__name__)


class Normalize(EffectParameterEditor):
    label = "Normalize"
    desc = "Normalizes audio such that any DC offset is removed"

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="max_amplitude",
            label='Max-Amplitude', 
            desc="Maximum amplitude",
            default=0.0,
            from_=-1,
            to=1,
            digits=1,
            resolution=0.1
        ).pack(side='top', fill='x', expand=True)

        LBoolean(
            self,
            pname="remove_dc_offset",
            label='Remove DC Offset', 
            desc="",
            default=True,
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.Normalize(
            max_amplitude=self.tkvars['max_amplitude'].get(),
            remove_dc_offset=self.tkvars['remove_dc_offset'].get(),
        )
        return effect

registry.add_effect('Normalize', Normalize)