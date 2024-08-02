import logging

import pedalboard
import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LScale,
)

log = logging.getLogger(__name__)


class HighShelfFilter(EffectParameterEditor):
    # I can't hear this doing anyting, but it does mess with the stream such that
    # you need to normalize to avoid range errors.
    label = "High Shelf Filter"
    desc = """A high shelf filter plugin with variable Q and gain, as would be used in an equalizer. Frequencies above the cutoff frequency will be boosted (or cut) by the provided gain (in decibels)."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="cutoff_frequency_hz",
            label='Cutoff Frequency (Hz)', 
            desc="",
            default=440,
            from_=-1,
            to=1000,
            digits=1,
            resolution=10
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="gain_db",
            label='Gain (db)', 
            desc="",
            default=0,
            from_=-0,
            to=20,
            digits=2,
            resolution=0.5
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="q",
            label='Q', 
            desc="the ratio of center frequency to bandwidth",
            default=0.707106,
            from_=-0,
            to=1,
            digits=3,
            resolution=0.01
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.HighShelfFilter(
                cutoff_frequency_hz=self.tkvars['cutoff_frequency_hz'].get(),
                gain_db=self.tkvars['gain_db'].get(), 
                q=self.tkvars['q'].get()
            )
        )
        return effect

registry.add_effect('HighShelfFilter', HighShelfFilter)