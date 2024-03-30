import tkinter as tk
from tkinter import ttk, font
import voicebox
import pedalboard

import logging
log = logging.getLogger('__name__')

WRAPLENGTH=250

class LScale(tk.Frame):
    def __init__(self, parent, label, desc, from_, to, variable, *args, digits=None, resolution=None, **kwargs):        
        super().__init__(parent, *args, **kwargs)
        tk.Label(
            self,
            text=label,
            anchor="e",
            wraplength=WRAPLENGTH,
            justify='left'
        ).pack(side='left', fill='x')
        
        tk.Scale(
            self,
            from_=from_,
            to=to,
            orient='horizontal',
            variable=variable,
            *args,
            digits=digits,
            resolution=resolution,
            **kwargs
        ).pack(side='left', fill='x', expand=True)


class LCombo(tk.Frame):
    def __init__(self, parent, label, desc, choices, variable, *args, **kwargs):        
        super().__init__(parent, *args, **kwargs)
        tk.Label(
            self,
            text=label,
            anchor="e",
            wraplength=WRAPLENGTH,
            justify='left'
        ).pack(side='left', fill='x')

        self.options = ttk.Combobox(
            self, 
            textvariable=variable
        )
        self.options['values'] = list(choices)
        self.options['state'] = 'readonly'
        
        self.options.pack(side='left', fill='x', expand=True)


class LBoolean(tk.Frame):
    def __init__(self, parent, label, desc, variable, *args, **kwargs):        
        super().__init__(parent, *args, **kwargs)
        tk.Label(
            self,
            text=label,
            anchor="e",
            wraplength=WRAPLENGTH,
            justify='left'
        ).pack(side='left', fill='x')
        
        self.options = ttk.Checkbutton(
            self, 
            text="",
            variable=variable,
            onvalue=True,
            offvalue=False
        )
        
        self.options.pack(side='left', fill='x', expand=True)

class EffectParameterEditor(tk.Frame):
    label = "Label"
    desc = "Description of effect"

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent
        topbar = tk.Frame(self)
        tk.Label(
            topbar,
            text=self.label,
            anchor="n",
            font=font.Font(weight="bold"),
            wraplength=WRAPLENGTH,
            justify='left'
        ).pack(side='left', fill='x', expand=True)
        
        tk.Button(
            topbar,
            text="X",
            anchor="center",
            width=1,
            height=1,
            command=self.remove_effect
        ).pack(side="right")
        topbar.pack(side="top", fill='x', expand=True)

        tk.Label(
            self,
            text=self.desc,
            anchor="n",
            wraplength=WRAPLENGTH,
            justify='left'
        ).pack(side='top', fill='x', expand=True)
    
    def get_effect(self):
        log.error(f'You must override get_effect() in {self} to return an instance of Effect()')
        return None
    
    def remove_effect(self):
        self.parent.remove_effect(self)
        # self.pack_forget()
        return

# scipy iir filters
IIR_FILTERS = ['butter', 'cheby1', 'cheby2', 'ellip', 'bessel']


class BandpassFilter(EffectParameterEditor):
    # https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.iirfilter.html
    label = "Bandpass Filter"
    desc = "analog bandpass filter between two frequencies"

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        

        self.low_frequency = tk.DoubleVar()
        self.high_frequency = tk.DoubleVar()
        self.order = tk.IntVar()
        self.type_ = tk.StringVar(value=IIR_FILTERS[0])

        LScale(
            self,
            'Low Frequency', 
            "Filter frequency in Hz",
            from_=100,
            to=4000,
            variable=self.low_frequency,
            resolution=100
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            'High Frequency', 
            "Filter frequency in Hz",
            from_=0,
            to=4000,
            variable=self.high_frequency,
            resolution=100
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            'Order', 
            "Higher orders will have faster dropoffs.",
            from_=0,
            to=10,
            variable=self.order,
        ).pack(side='top', fill='x', expand=True)

        LCombo(
            self,
            'Type',
            'type of IIR filter to design',
            choices=IIR_FILTERS,
            variable=self.type_
        ).pack(side='top', fill='x', expand=True)

        # TODO:
        # this is incomplete, when users choose chebyshev or elliptic they should
        # also get widget to set the ripple and min attenuation

    def get_effect(self):
        log.info('get_effect()')
        effect = voicebox.effects.Filter.build(
            btype='bandpass',
            freq=(self.low_frequency.get(), self.high_frequency.get()),
            order=self.order.get(),
            rp=None,
            rs=None,
            ftype=self.type_.get()
        )
        return effect

class BandstopFilter(EffectParameterEditor):
    # https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.iirfilter.html
    label = "Bandstop Filter"
    desc = "analog bandstop filter between two frequencies"

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.low_frequency = tk.DoubleVar()
        self.high_frequency = tk.DoubleVar()
        self.order = tk.IntVar()
        self.type_ = tk.StringVar(value=IIR_FILTERS[0])

        LScale(
            self,
            'Low Frequency', 
            "Filter frequency in Hz",
            from_=0,
            to=4000,
            variable=self.low_frequency,
            resolution=100
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            'High Frequency', 
            "Filter frequency in Hz",
            from_=0,
            to=4000,
            variable=self.high_frequency,
            resolution=100
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            'Order', 
            "Higher orders will have faster dropoffs.",
            from_=0,
            to=10,
            variable=self.order,
        ).pack(side='top', fill='x', expand=True)

        LCombo(
            self,
            'Type',
            'type of IIR filter to design',
            choices=IIR_FILTERS,
            variable=self.type_
        ).pack(side='top', fill='x', expand=True)

        # TODO:
        # this is incomplete, when users choose chebyshev or elliptic they should
        # also get widget to set the ripple and min attenuation

    def get_effect(self):
        effect = voicebox.effects.Filter.build(
            btype='bandstop',
            freq=(self.low_frequency.get(), self.high_frequency.get()),
            order=self.order.get(),
            rp=None,
            rs=None,
            ftype=self.type_.get()
        )
        return effect

class LowpassFilter(EffectParameterEditor):
    # https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.iirfilter.html
    label = "Lowpass Filter"
    desc = "lowpass filter for signals below a frequency"

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.frequency = tk.DoubleVar()
        self.order = tk.IntVar()
        self.type_ = tk.StringVar(value=IIR_FILTERS[0])

        LScale(
            self,
            'Frequency', 
            "Filter frequency in Hz",
            from_=0,
            to=4000,
            variable=self.low_frequency,
            resolution=100
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            'Order', 
            "Higher orders will have faster dropoffs.",
            from_=0,
            to=10,
            variable=self.order,
        ).pack(side='top', fill='x', expand=True)

        LCombo(
            self,
            'Type',
            'type of IIR filter to design',
            choices=IIR_FILTERS,
            variable=self.type_
        ).pack(side='top', fill='x', expand=True)

        # TODO:
        # this is incomplete, when users choose chebyshev or elliptic they should
        # also get widget to set the ripple and min attenuation

    def get_effect(self):
        effect = voicebox.effects.Filter.build(
            btype='lowpass',
            freq=self.frequency.get(),
            order=self.order.get(),
            rp=None,
            rs=None,
            ftype=self.type_.get()
        )
        return effect

class HighpassFilter(EffectParameterEditor):
    # https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.iirfilter.html
    label = "Highass Filter"
    desc = "Highpass filter for signals above a frequency"

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.frequency = tk.DoubleVar()
        self.order = tk.IntVar()
        self.type_ = tk.StringVar(value=IIR_FILTERS[0])

        LScale(
            self,
            'Frequency', 
            "Filter frequency in Hz",
            from_=0,
            to=4000,
            variable=self.low_frequency,
            resolution=100
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            'Order', 
            "Higher orders will have faster dropoffs.",
            from_=0,
            to=10,
            variable=self.order,
        ).pack(side='top', fill='x', expand=True)

        LCombo(
            self,
            'Type',
            'type of IIR filter to design',
            choices=IIR_FILTERS,
            variable=self.type_
        ).pack(side='top', fill='x', expand=True)

        # TODO:
        # this is incomplete, when users choose chebyshev or elliptic they should
        # also get widget to set the ripple and min attenuation

    def get_effect(self):
        effect = voicebox.effects.Filter.build(
            btype='highpass',
            freq=self.frequency.get(),
            order=self.order.get(),
            rp=None,
            rs=None,
            ftype=self.type_.get()
        )
        return effect

class Glitch(EffectParameterEditor):
    label = "Glitch"
    desc = "Creates a glitchy sound by randomly repeating small chunks of audio."

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.chunk_time = tk.DoubleVar()
        self.p_repeat = tk.DoubleVar()
        self.max_repeats = tk.IntVar()

        LScale(
            self,
            'Chunk Time', 
            "Length of each repeated chunk, in seconds.",
            from_=0.01,
            to=2,
            variable=self.chunk_time,
            digits=3,
            resolution=0.01
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            'Prob. Repeat', 
            "Probability of repeating each chunk.",
            from_=0,
            to=1,
            variable=self.p_repeat,
            digits=3,
            resolution=0.01
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            'Max Repeat', 
            "Maximum number of times to repeat each chunk.",
            from_=1,
            to=5,
            variable=self.max_repeats,
            digits=1,
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        log.info('get_effect()')
        effect = voicebox.effects.Glitch(
            chunk_time=self.chunk_time.get(),
            p_repeat=self.p_repeat.get(),
            max_repeats=self.max_repeats.get()
        )
        return effect

class Normalize(EffectParameterEditor):
    label = "Normalize"
    desc = "Normalizes audio such that any DC offset is removed"

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.max_amplitude = tk.DoubleVar()
        self.remove_dc_offset = tk.BooleanVar(value=True)

        LScale(
            self,
            'Max-Amplitude', 
            "Maximum amplitude in Hz",
            from_=0,
            to=2,
            variable=self.max_amplitude,
            digits=3,
            resolution=0.01
        ).pack(side='top', fill='x', expand=True)

        LBoolean(
            self,
            'Remove DC Offset', 
            "",
            variable=self.remove_dc_offset,
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.Normalize(
            max_amplitude=self.max_amplitude.get(),
            remove_dc_offset=self.remove_dc_offset.get(),
        )
        return effect

class Bitcrush(EffectParameterEditor):
    label = "Bitcrush"
    desc = "reduces the signal to a given bit depth, giving the audio a lo-fi, digitized sound."

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.bit_depth = tk.DoubleVar()

        LScale(
            self,
            'Bit Depth', 
            "Bit depth to quantize the signal to.",
            from_=0,
            to=32,
            variable=self.bit_depth,
            digits=2,
            resolution=0.25
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Bitcrush(
                bit_depth=self.bit_depth.get()
            )
        )
        return effect

EFFECTS = {
    # Cosmetic : Object
    'Bandpass Filter': BandpassFilter,
    'Bandstop Filter': BandstopFilter,
    'Bitcrush': Bitcrush, # Pedalboard
    # 'Chorus': None, # Pedalboard
    # 'Clipping': None, # Pedalboard
    # 'Compressor': None, # Pedalboard
    # 'Delay': None, # Pedalboard
    # 'Distortion': None, # Pedalboard
    # 'Gain': None, # Pedalboard
    'Glitch': Glitch,
    # 'GSMFullRateCompressor': None, # Pedalboard
    'Highpass Filter': HighpassFilter,
    # 'HighShelfFilter': None, # Pedalboard
    # 'LadderFilter': None, # Pedalboard
    # 'Limiter': None, # Pedalboard
    'Lowpass Filter': LowpassFilter,
    # 'LowShelfFilter': None, # Pedalboard
    # 'MP3Compressor': None, # Pedalboard
    # 'NoiseGate': None, # Pedalboard
    'Normalize': Normalize,
    # 'PeakFilter': None, # Pedalboard
    # 'Phaser': None, # Pedalboard
    # 'PitchShift': None, # Pedalboard
    # 'Remove DC Offset': None,
    # 'Resample': None, # Pedalboard
    # 'Reverb': None, # Pedalboard
    # 'RingMod': {},
    # 'Vocoder': {},
}
