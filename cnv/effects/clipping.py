import logging

import pedalboard
import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LScale,
)

log = logging.getLogger(__name__)


class Clipping(EffectParameterEditor):
    label = "clipping"
    desc = """A distortion plugin that adds hard distortion to the signal by clipping the signal at the provided threshold (in decibels)."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="threshold_db",
            label='Threshold (db)', 
            desc="",
            default=-6.0,
            from_=-10,
            to=10,
            digits=1,
            resolution=0.5
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Clipping(
                threshold_db=self.tkvars['threshold_db'].get(), 
            )
        )
        return effect

registry.add_effect('Clipping', Clipping)