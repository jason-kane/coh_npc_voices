import logging

import pedalboard
import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LCombo,
    LScale,
)

log = logging.getLogger(__name__)


class LadderFilter(EffectParameterEditor):
    label = "Ladder Filter"
    desc = """A multi-mode audio filter based on the classic Moog synthesizer ladder filter, invented by Dr. Bob Moog in 1968.

Depending on the filter’s mode, frequencies above, below, or on both sides of the cutoff frequency will be attenuated. Higher values for the resonance parameter may cause peaks in the frequency response around the cutoff frequency."""
    mode_choices = [
        "LPF12 low-pass 12dB filter",
        "HPF12 high-pass 12dB filter",
        "BPF12 band-pass 12dB filter",
        "LPF24 low-pass 24dB filter",
        "HPF24 high-pass 24dB filter",
        "BPF24 band-pass 24dB filter",
    ]

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LCombo(
            self,
            pname="mode",
            label="Mode",
            desc="The type of filter architecture to use.",
            default=self.mode_choices[0],
            choices=self.mode_choices
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="cutoff_hz",
            label='Cutoff (Hz)', 
            desc="",
            default=200,
            from_=0,
            to=1000,
            digits=1,
            resolution=10
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="resonance",
            label='Resonance', 
            desc="",
            default=0,
            from_=-0,
            to=1,
            digits=2,
            resolution=0.1
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="drive",
            label='Drive (db?)', 
            desc="",
            default=1.0,
            from_=0,
            to=10,
            digits=3,
            resolution=0.5
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.LadderFilter(
                mode=getattr(pedalboard.LadderFilter.Mode, self.mode.get().split()[0]),
                # self.mode_choices.index(),
                cutoff_hz=self.tkvars['cutoff_hz'].get(), 
                resonance=self.tkvars['resonance'].get(),
                drive=self.tkvars['drive'].get()
            )
        )
        return effect

registry.add_effect('LadderFilter', LadderFilter)