import logging

import pedalboard
import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LScale,
)

log = logging.getLogger(__name__)


class PitchShift(EffectParameterEditor):
    label = "PitchShift"
    desc = "A pitch shifting effect that can change the pitch of audio without affecting its duration."

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="semitones",
            label='Semitones', 
            desc="How far to shift the pitch",
            default=0.5,
            from_=-8,
            to=8,
            digits=2,
            resolution=0.25
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.PitchShift(
                semitones=self.tkvars['semitones'].get(), 
            )
        )
        return effect

registry.add_effect('PitchShift', PitchShift)