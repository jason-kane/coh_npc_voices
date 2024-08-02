import logging

import pedalboard
import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LScale,
)

log = logging.getLogger(__name__)


class Gain(EffectParameterEditor):
    label = "gain"
    desc = """A gain plugin that increases or decreases the volume of a signal by amplifying or attenuating it by the provided value (in decibels). No distortion or other effects are applied.
        Think of this as a volume control."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="gain_db",
            label='Gain (db)', 
            desc="",
            default=1,
            from_=-1,
            to=20,
            digits=2,
            resolution=0.5
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Gain(
                gain_db=self.tkvars['gain_db'].get(), 
            )
        )
        return effect

registry.add_effect('Gain', Gain)