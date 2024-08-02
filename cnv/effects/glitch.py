import logging

import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LScale,
)

log = logging.getLogger(__name__)


class Glitch(EffectParameterEditor):
    label = "Glitch"
    desc = "Creates a glitchy sound by randomly repeating small chunks of audio."

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="chunk_time",
            label='Chunk Time', 
            desc="Length of each repeated chunk, in seconds.",
            default=0.01,
            from_=0.01,
            to=2,
            digits=3,
            resolution=0.01
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="p_repeat",
            label='Prob. Repeat', 
            desc="Probability of repeating each chunk.",
            default=0,
            from_=0,
            to=1,
            digits=3,
            resolution=0.01
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="max_repeats",
            label='Max Repeat', 
            desc="Maximum number of times to repeat each chunk.",
            default=1,
            from_=1,
            to=5,
            digits=1,
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        log.debug('get_effect()')
        effect = voicebox.effects.Glitch(
            chunk_time=self.tkvars['chunk_time'].get(),
            p_repeat=self.tkvars['p_repeat'].get(),
            max_repeats=int(self.tkvars['max_repeats'].get())
        )
        return effect

registry.add_effect('Glitch', Glitch)