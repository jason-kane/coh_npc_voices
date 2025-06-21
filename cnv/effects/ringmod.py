import logging

import numpy as np
import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LCombo,
    LScale,
)

log = logging.getLogger(__name__)


class RingMod(EffectParameterEditor):
    label = "Ringmod"
    desc = ("Multiplies the audio signal by a carrier wave. Can be used "
            "to create choppy, Doctor Who Dalek-like effects at low carrier "
            "frequencies, or bell-like sounds at higher carrier frequencies")

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="carrier_freq",
            label='Carrier Freq (Hz)', 
            desc="Frequency of the carrier wave in Hz.",
            default=160,
            from_=0,
            to=1000,
            digits=0,
            resolution=10
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="blend",
            label='Signal Blend', 
            desc="Blend between the original and modulated signals.  0 is all original, 1 is all modulated.",
            default=0.5,
            from_=0,
            to=1,
            digits=0,
            resolution=0.01
        ).pack(side='top', fill='x', expand=True)

        LCombo(
            self,
            pname="carrier_wave",
            label='Carrier wave',
            desc='Numpy Carrier wave function',
            default="sin",
            choices=["sin", "cos"],
        ).pack(side='top', fill='x', expand=True)


    def get_effect(self):
        effect = voicebox.effects.RingMod(
            carrier_freq=self.tkvars['carrier_freq'].get(),
            blend=self.tkvars['blend'].get(),
            # ie: np.sin.get() or np.cos.get()
            carrier_wave=getattr(np, self.tkvars['carrier_wave'].get())
        )
        return effect


registry.add_effect('RingMod', RingMod)