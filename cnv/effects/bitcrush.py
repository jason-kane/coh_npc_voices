import logging

import pedalboard
import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LScale,
)

log = logging.getLogger(__name__)


class Bitcrush(EffectParameterEditor):
    label = "Bitcrush"
    desc = "reduces the signal to a given bit depth, giving the audio a lo-fi, digitized sound."

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="bit_depth",
            label='Bit Depth', 
            desc="Bit depth to quantize the signal to.",
            default=32,
            from_=0,
            to=32,
            digits=2,
            resolution=0.25
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Bitcrush(
                bit_depth=self.tkvars['bit_depth'].get()
            )
        )
        return effect

registry.add_effect('Bitcrush', Bitcrush)