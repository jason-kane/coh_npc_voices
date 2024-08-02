import logging

import pedalboard
import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LBoolean,
    LScale,
)

log = logging.getLogger(__name__)


class Reverb(EffectParameterEditor):
    label = "Reverb"
    desc = (
        "A simple reverb effect. Uses a simple stereo reverb algorithm, based "
        "on the technique and tunings used in FreeVerb "
        "<https://ccrma.stanford.edu/~jos/pasp/Freeverb.html>_.  "
        "The delay lengths are optimized for a sample rate of 44100 Hz."
    )

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="room_size",
            label='Room size', 
            desc="Room Size",
            default=0.4,
            from_=0.05,
            to=1,
            digits=3,
            resolution=0.05
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="damping",
            label='Damping', 
            desc="damping parameter [0=low damping, 1=higher damping]",
            default=0.4,
            from_=0.05,
            to=1,
            digits=3,
            resolution=0.05
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="wet_level",
            label='Wet level', 
            desc="Wet Level",
            default=0.4,
            from_=0.05,
            to=1,
            digits=3,
            resolution=0.05
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="dry_level",
            label='Dry level', 
            desc="Dry Level",
            default=0.4,
            from_=0.05,
            to=1,
            digits=3,
            resolution=0.05
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="width",
            label='Width', 
            desc="width (left-right mixing) parameter",
            default=0.4,
            from_=0.05,
            to=1,
            digits=3,
            resolution=0.05
        ).pack(side='top', fill='x', expand=True)

        LBoolean(
            self,
            pname="freeze_mode",
            label='Freeze mode', 
            desc="frozen/unfrozen",
            default=False
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Reverb(
                room_size=self.tkvars['room_size'].get(), 
                damping=self.tkvars['damping'].get(), 
                wet_level=self.tkvars['wet_level'].get(),
                dry_level=self.tkvars['dry_level'].get(), 
                width=self.tkvars['width'].get(), 
                freeze_mode= 1 if self.tkvars['freeze_mode'].get() else 0
            )
        )
        return effect

registry.add_effect('Reverb', Reverb)