import logging

import voicebox

from cnv.effects.base import (
    registry,
    IIR_FILTERS,
    EffectParameterEditor,
    LCombo,
    LScale,
)

log = logging.getLogger(__name__)


class BandstopFilter(EffectParameterEditor):
    # https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.iirfilter.html
    label = "Bandstop Filter"
    desc = "analog bandstop filter between two frequencies"

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname='low_frequency',
            label='Low Frequency', 
            desc="Filter frequency in Hz",
            default=100,
            from_=100,
            to=4000,
            resolution=100
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="high_frequency",
            label='High Frequency', 
            desc="Filter frequency in Hz",
            default=600,
            from_=1,
            to=4000,
            resolution=100
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="order",
            label='Order', 
            desc="Higher orders will have faster dropoffs.",
            default=0,
            from_=0,
            to=10,
        ).pack(side='top', fill='x', expand=True)

        LCombo(
            self,
            pname="type_",
            label='Type',
            desc='type of IIR filter to design',
            default="butter",
            choices=IIR_FILTERS,
        ).pack(side='top', fill='x', expand=True)

        # TODO:
        # this is incomplete, when users choose chebyshev or elliptic they should
        # also get widget to set the ripple and min attenuation

    def get_effect(self):
        effect = voicebox.effects.Filter.build(
            btype='bandstop',
            freq=(
                self.tkvars['low_frequency'].get(), 
                self.tkvars['high_frequency'].get()
            ),
            order=self.tkvars['order'].get(),
            rp=None,
            rs=None,
            ftype=self.tkvars['type_'].get()
        )
        return effect

registry.add_effect('Bandstop Filter', BandstopFilter)