import logging

import pedalboard
import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LScale,
)

log = logging.getLogger(__name__)


class Distortion(EffectParameterEditor):
    label = "distortion"
    desc = """A distortion effect, which applies a non-linear (tanh, or hyperbolic tangent) waveshaping function to apply harmonically pleasing distortion to a signal."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="drive_db",
            label='Drive (db)', 
            desc="",
            default=25,
            from_=-1,
            to=50,
            digits=1,
            resolution=1
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Distortion(
                drive_db=self.tkvars['drive_db'].get(), 
            )
        )
        return effect

registry.add_effect('Distortion', Distortion)