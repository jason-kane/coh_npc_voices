import logging

import pedalboard
import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LScale,
)

log = logging.getLogger(__name__)


class Delay(EffectParameterEditor):
    label = "Delay"
    desc = """A digital delay plugin with controllable delay time, feedback percentage, and dry/wet mix."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="delay_seconds",
            label='Delay (sec)', 
            desc="",
            default=0.25,
            from_=-0.1,
            to=0.5,
            digits=3,
            resolution=0.01
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="feedback",
            label='Feedback (%)', 
            desc="",
            default=0.0,
            from_=0,
            to=1,
            digits=2,
            resolution=0.05
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="mix",
            label='Mix', 
            desc="",
            default=0.5,
            from_=0,
            to=1,
            digits=2,
            resolution=0.1
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Delay(
                delay_seconds=self.tkvars['delay_seconds'].get(), 
                feedback=self.tkvars['feedback'].get(),
                mix=self.tkvars['mix'].get(),
            )
        )
        return effect

registry.add_effect('Delay', Delay)