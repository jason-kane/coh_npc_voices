import logging

import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LScale,
)

log = logging.getLogger(__name__)


class Vocoder(EffectParameterEditor):
    label = "Vocoder"
    desc = "Vocoder effect. Useful for making monotone, robotic voices."

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="carrier_freq",
            label='Carrier Freq (Hz)', 
            desc="Frequency of the carrier wave in Hz.",
            default=160,
            from_=0,
            to=200,
            digits=0,
            resolution=2
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="min_freq",
            label='Minimum Freq (Hz)', 
            desc="Minimum frequency of the bandpass filters in Hz.",
            default=80,
            from_=0,
            to=500,
            digits=0,
            resolution=5
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="max_freq",
            label='Maximum Freq (Hz)', 
            desc="Maximum frequency of the bandpass filters in Hz.\nShould be <= half the sample rate of the audio.",
            default=8000,
            from_=0,
            to=10000,
            digits=0,
            resolution=100
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="bands",
            label='Bands', 
            desc=" Number of bands to divide the frequency range into.\nMore bands increases reconstruction quality.",
            default=40,
            from_=1,
            to=100,
            digits=0,
            resolution=1,
            _type=int
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="bandwidth",
            label='Bandwidth', 
            desc=" Bandwidth of each band, as a fraction of its maximum width.",
            default=0.5,
            from_=0,
            to=1,
            digits=2,
            resolution=0.1
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="bandpass_filter_order",
            label='Bandpass order', 
            desc="Bandpass filter order. Higher orders have steeper rolloffs",
            default=3,
            from_=0,
            to=32,
            digits=0,
            resolution=1
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.Vocoder.build(
            carrier_freq=self.tkvars['carrier_freq'].get(),
            min_freq=self.tkvars['min_freq'].get(),
            max_freq=self.tkvars['max_freq'].get(),
            bands=int(self.tkvars['bands'].get()),
            bandwidth=self.tkvars['bandwidth'].get(),
            bandpass_filter_order=self.tkvars['bandpass_filter_order'].get()
        )
        return effect

registry.add_effect('Vocoder', Vocoder)