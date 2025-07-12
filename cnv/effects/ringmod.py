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

        # LScale(
        #     self,
        #     pname="blend",
        #     label='Signal Blend', 
        #     desc="Blend between the original and modulated signals.  0 is all original, 1 is all modulated.",
        #     default=0.5,
        #     from_=0,
        #     to=1,
        #     digits=0,
        #     resolution=0.01
        # ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="dry",
            label='Dry', 
            desc="Dry",
            default=0.5,
            from_=0,
            to=1,
            digits=1,
            resolution=0.1
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="wet",
            label='Wet', 
            desc="Wet",
            default=0.5,
            from_=0,
            to=1,
            digits=1,
            resolution=0.1
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
        # def __init__(
        #         self,
        #         carrier_freq: float = 20.,
        #         carrier_wave: WaveFunc = np.sin,
        #         dry: float = 0.5,
        #         wet: float = 0.5,
        # ):       
        carrier_freq = self.tkvars['carrier_freq'].get()
        
        # ie: np.sin.get() or np.cos.get()
        carrier_wave = getattr(np, self.tkvars['carrier_wave'].get())

        wet = self.tkvars['wet'].get()
        dry = self.tkvars['dry'].get()

        log.debug(f"get_effect() -> RingMod({carrier_freq=}, {carrier_wave=}, {dry=}, {wet=})") 
        effect = voicebox.effects.RingMod(
            carrier_freq=carrier_freq,
            carrier_wave=carrier_wave,
            dry=dry,
            wet=wet
        )
        return effect


registry.add_effect('RingMod', RingMod)