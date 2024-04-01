import logging
import tkinter as tk
from tkinter import font, ttk

import pedalboard
import voicebox
from db import commit, get_cursor

log = logging.getLogger('__name__')

WRAPLENGTH=250

class LScale(tk.Frame):
    def __init__(
        self,
        parent,
        pname,
        label,
        desc,
        default,
        from_,
        to,
        *args, digits=None, resolution=None, **kwargs
    ):
        super().__init__(parent, *args, **kwargs)
        variable = tk.DoubleVar(
            name=f"{pname}",
            value=default
        )
        variable.trace_add("write", parent.reconfig)
        setattr(parent, pname, variable)
        parent.parameters.append(pname)

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

    def __init__(self,
        parent,
        pname,
        label, 
        desc,
        default,
        choices, 
        *args, **kwargs
    ): 
        super().__init__(parent, *args, **kwargs)

        variable = tk.StringVar(value=default)
        variable.trace_add("write", parent.reconfig)
        setattr(parent, pname, variable)
        parent.parameters.append(pname)

        tk.Label(
            self,
            text=label,
            anchor="e",
            wraplength=WRAPLENGTH,
            justify='left'
        ).pack(side='left', fill='x')

        options = ttk.Combobox(
            self, 
            textvariable=variable
        )
        options['values'] = list(choices)
        options['state'] = 'readonly'
            
        options.pack(side='left', fill='x', expand=True)


class LBoolean(tk.Frame):
    def __init__(
        self,
        parent,
        pname,
        label,
        desc,
        default,
        variable,
        *args, **kwargs
    ):
        super().__init__(parent, *args, **kwargs)
        variable = tk.BooleanVar(
            name=f"{pname}",
            value=default
        )
        variable.trace_add("write", parent.reconfig)
        setattr(parent, pname, variable)
        parent.parameters.append(pname)  

        tk.Label(
            self,
            text=label,
            anchor="e",
            wraplength=WRAPLENGTH,
            justify='left'
        ).pack(side='left', fill='x')  

        ttk.Checkbutton(
            self, 
            text="",
            variable=variable,
            onvalue=True,
            offvalue=False
        ).pack(side='left', fill='x', expand=True)


class EffectParameterEditor(tk.Frame):
    label = "Label"
    desc = "Description of effect"

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent  # parent is the effectlist
        self.effect_id = tk.IntVar()
        self.parameters = []

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

    def reconfig(self, varname, lindex, operation):
        """
        The user changed one of the parameters.  Lets
        persist that change.  Make the database reflect
        the UI.
        """
        log.info(f'reconfig triggered by {varname}')
        cursor = get_cursor()
        effect_id = self.effect_id.get()

        effect_setting = cursor.execute("""
            SELECT 
                id, key, value
            FROM
                effect_setting
            where
                effect_id = ?
        """, (
            effect_id,
        )).fetchall()

        log.info('Sync to db')
        for id, key, value in effect_setting:
            value = float(value)

            try:
                new_value = getattr(self, key).get()
            except AttributeError:
                log.error(f'Invalid configuration.  Cannot set {key} on a {self} effect.')
                continue

            if new_value != value:
                log.info(f'Saving changed value {id}:{key} {value!r}=>{new_value!r}')
                # this value is different than what
                # we have in the database
                cursor.execute("""
                    UPDATE
                        effect_setting
                    SET
                        value=?
                    WHERE
                        id=?
                """, (str(new_value), id, ))
            else:
                log.info(f'Value for {key} has not changed')

        commit()


# scipy iir filters
IIR_FILTERS = ['butter', 'cheby1', 'cheby2', 'ellip', 'bessel']


class BandpassFilter(EffectParameterEditor):
    # https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.iirfilter.html
    label = "Bandpass Filter"
    desc = "analog bandpass filter between two frequencies"

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
            default=0,
            from_=0,
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

        LScale(
            self,
            pname="max_amplitude",
            label='Max-Amplitude', 
            desc="Maximum amplitude in Hz",
            default=0,
            from_=0,
            to=2,
            digits=3,
            resolution=0.01
        ).pack(side='top', fill='x', expand=True)

        LBoolean(
            self,
            pname="remove_dc_offset",
            label='Remove DC Offset', 
            desc="",
            default=True,
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

        LScale(
            self,
            pname="bit_depth",
            label='Bit Depth', 
            desc="Bit depth to quantize the signal to.",
            default=32,
            from_=0,
            to=32,
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
            resolution=1
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
            resolution=0.5
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
                'rate_hz': self.rate_hz.get(), 
                'depth': self.depth.get(), 
                'centre_delay_ms': self.centre_delay_ms.get(), 
                'feedback': self.feedback.get(), 
                'mix': self.mix.get()
            }

        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Chorus(**values)
        )
        return effect

class Clipping(EffectParameterEditor):
    label = "clipping"
    desc = """A distortion plugin that adds hard distortion to the signal by clipping the signal at the provided threshold (in decibels)."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="threshold_db",
            label='Threshold (db)', 
            desc="",
            default=-6.0,
            from_=-10,
            to=10,
            digits=1,
            resolution=0.5
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Clipping(
                threshold_db=self.threshold_db.get(), 
            )
        )
        return effect

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
                threshold_db=self.threshold_db.get(), 
                ratio=self.ratio.get(),
                attack_ms=self.attack_ms.get(),
                release_ms=self.release_ms.get()
            )
        )
        return effect

EFFECTS = {
    # Cosmetic : Object
    'Bandpass Filter': BandpassFilter,
    'Bandstop Filter': BandstopFilter,
    'Bitcrush': Bitcrush, # Pedalboard
    'Chorus': Chorus, # Pedalboard
    'Clipping': Clipping, # Pedalboard
    'Compressor': Compressor, # Pedalboard
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
