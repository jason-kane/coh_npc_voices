import logging

import pedalboard
import voicebox

from cnv.effects.base import (
    registry,
    EffectParameterEditor,
    LScale,
)

log = logging.getLogger(__name__)


class Chorus(EffectParameterEditor):
    label = "chorus"
    desc = """A basic chorus effect.
    This audio effect can be controlled via the speed and depth of the LFO controlling the frequency response, a mix control, a feedback control, and the centre delay of the modulation.
    Note: To get classic chorus sounds try to use a centre delay time around 7-8 ms with a low feeback volume and a low depth. This effect can also be used as a flanger with a lower centre delay time and a lot of feedback, and as a vibrato effect if the mix value is 1.
    """

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        
        LScale(
            self,
            pname="rate_hz",
            label='Rate (Hz)', 
            desc="The speed of the chorus effect’s low-frequency oscillator (LFO), in Hertz. This value must be between 0 Hz and 100 Hz.",
            default=1.0,
            from_=0,
            to=100,
            digits=0,
            resolution=5
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="depth",
            label='Depth', 
            desc="",
            default=0.25,
            from_=0,
            to=5,
            digits=0,
            resolution=0.125
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="centre_delay_ms",
            label='Center delay (ms)', 
            desc="",
            default=7.0,
            from_=0,
            to=50,
            digits=1,
            resolution=1
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="feedback",
            label='Feedback', 
            desc="",
            default=0.0,
            from_=0,
            to=1,
            digits=2,
            resolution=0.1
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
    
    def get_effect(self, values=None):
        if values is None:
            values = {
                'rate_hz': self.tkvars['rate_hz'].get(), 
                'depth': self.tkvars['depth'].get(), 
                'centre_delay_ms': self.tkvars['centre_delay_ms'].get(), 
                'feedback': self.tkvars['feedback'].get(), 
                'mix': self.tkvars['mix'].get()
            }

        # The returned array may contain up to (but not more than) the same
        # number of samples as were provided. If fewer samples were returned
        # than expected, the plugin has likely buffered audio inside itself. To
        # receive the remaining audio, pass another audio buffer into process
        # with reset set to True.
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Chorus(**values)
        )
        return effect

registry.add_effect('Chorus', Chorus)