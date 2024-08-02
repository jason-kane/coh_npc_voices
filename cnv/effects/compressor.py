import logging

import pedalboard
import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LScale,
)

log = logging.getLogger(__name__)


class Compressor(EffectParameterEditor):
    label = "compressor"
    desc = """A dynamic range compressor, used to reduce the volume of loud sounds and “compress” the loudness of the signal."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="threshold_db",
            label='Threshold (db)', 
            desc="",
            default=0.0,
            from_=-10,
            to=10,
            digits=1,
            resolution=0.5
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="ratio",
            label='Ratio', 
            desc="",
            default=1.0,
            from_=0,
            to=10,
            digits=1,
            resolution=0.5
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="attack_ms",
            label='Attack (ms)', 
            desc="",
            default=1.0,
            from_=0,
            to=20,
            digits=1,
            resolution=1
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="release_ms",
            label='Release (ms)', 
            desc="",
            default=100.0,
            from_=0,
            to=200,
            digits=0,
            resolution=10
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Compressor(
                threshold_db=self.tkvars['threshold_db'].get(), 
                ratio=self.tkvars['ratio'].get(),
                attack_ms=self.tkvars['attack_ms'].get(),
                release_ms=self.tkvars['release_ms'].get()
            )
        )
        return effect

registry.add_effect('Compressor', Compressor)