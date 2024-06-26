import logging
import tkinter as tk
from tkinter import font, ttk

import cnv.database.models as models
import numpy as np
import pedalboard
import voicebox
from sqlalchemy import select
from tkfeather import Feather

log = logging.getLogger(__name__)

WRAPLENGTH=350

class LScale(ttk.Frame):
    """
    Labeled choose-a-number
    """
    def __init__(
        self,
        parent,
        pname,
        label,
        desc,
        default,
        from_,
        to,
        _type=float,
        *args, digits=None, resolution=0, **kwargs
    ):
        super().__init__(parent, *args, **kwargs)
        self.columnconfigure(0, minsize=125, uniform="effect")
        self.columnconfigure(1, weight=2, uniform="effect")
        
        if _type == int:
            variable = tk.IntVar(
                name=f"{parent.label.lower()}_{pname}",
                value=default
            )
        else:
            variable = tk.DoubleVar(
                name=f"{parent.label.lower()}_{pname}",
                value=default
            )

        # label for the setting
        ttk.Label(
            self,
            text=label,
            anchor="e",
            justify='right'
        ).grid(row=0, column=0, sticky='e')

        # widget for viewing/changing the value
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
        ).grid(row=0, column=1, sticky='ew')

        setattr(parent, pname, variable)
        parent.parameters.append(pname)


class LCombo(ttk.Frame):
    """
    Combo widget to select a string from a set of possible values
    """
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

        # label for the setting
        ttk.Label(
            self,
            text=label,
            anchor="e",
            justify='right'
        ).grid(row=0, column=0, sticky='e')

        # widget for viewing/changing the value
        options = ttk.Combobox(
            self, 
            textvariable=variable
        )
        options['values'] = list(choices)
        options['state'] = 'readonly'
            
        options.grid(row=0, column=1, sticky='ew')

        setattr(parent, pname, variable)
        parent.parameters.append(pname)        


class LBoolean(ttk.Frame):
    def __init__(
        self,
        parent,
        pname,
        label,
        desc,
        default,
        *args, **kwargs
    ):
        super().__init__(parent, *args, **kwargs)

        variable = tk.BooleanVar(
            name=f"{pname}",
            value=default
        )

        # label for the setting
        ttk.Label(
            self,
            text=label,
            anchor="e",
            justify='right'
        ).grid(row=0, column=0, sticky='e')

        # widget for viewing/changing the value
        ttk.Checkbutton(
            self, 
            text="",
            variable=variable,
            onvalue=True,
            offvalue=False
        ).grid(row=0, column=0, sticky='ew')

        setattr(parent, pname, variable)
        parent.parameters.append(pname)  


class EffectParameterEditor(ttk.Frame):
    label = "Label"
    desc = "Description of effect"

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent  # parent is the effectlist
        self.effect_id = tk.IntVar()
        self.parameters = []
        self.traces = {}
        self.trashcan = Feather("trash-2", size=24)

        topbar = ttk.Frame(self)
        # the name of this effect
        ttk.Label(
            topbar,
            text=self.label.title(),
            anchor="n",
            font=font.Font(
                size=18,
                weight="bold"
            )
        ).pack(side='left', fill='x', expand=True)
    
        ttk.Style().configure(
            "CloseFrame.TButton",
            anchor="center",
            width=1,
            height=1
        )

        # delete button
        ttk.Button(
            topbar,
            image=self.trashcan.icon,
            style="CloseFrame.TButton",
            command=self.remove_effect
        ).place(relx=1, rely=0, anchor='ne')

        topbar.pack(side="top", fill='x', expand=True)

        # the descriptive text for this effect
        ttk.Label(
            self,
            text=self.desc,
            anchor="n",
            wraplength=WRAPLENGTH,
            justify='left'
        ).pack(side='top', fill='x', expand=True)
    
    def get_effect(self):
        log.error(f'You must override get_effect() in {self} to return an instance of Effect()')
        return None
    
    def clear_traces(self):
        log.debug('Clearing traces...')
        for trace_var in self.traces:
            log.debug(f'{trace_var=}')
            for trace in self.traces[trace_var].trace_info():
                log.debug(f"trace: {trace!r}")
                self.traces[trace_var].trace_remove(trace[0], trace[1])

    def remove_effect(self):
        log.debug("EffectParamaterEngine.remove_effect()")
        # remove any variable traces
        self.clear_traces()
        self.parent.remove_effect(self)
        return

    def reconfig(self, varname, lindex, operation):
        """
        The user changed one of the effect parameters.  Lets
        persist that change.  Make the database reflect
        the UI.
        """
        log.debug(f'reconfig triggered by {varname}/{lindex}/{operation}')
        effect_id = self.effect_id.get()

        with models.Session(models.engine) as session:
            # fragile, varname is what is coming off the trace trigger
            log.debug(f'Reading effects settings when {effect_id=}')
            effect_settings = session.scalars(
                select(models.EffectSetting).where(
                    models.EffectSetting.effect_id==effect_id
                )
            ).all()

            log.debug(f'Sync to db {effect_settings}')
            found = set()
            for effect_setting in effect_settings:
                found.add(effect_setting.key)
                try:
                    new_value = str(getattr(self, effect_setting.key).get())
                except AttributeError:
                    log.error(f'Invalid configuration.  Cannot set {effect_setting.key} on a {self} effect.')
                    continue

                if new_value != effect_setting.value:
                    log.debug(f'Saving changed value {effect_setting.key} {effect_setting.value!r}=>{new_value!r}')
                    # this value is different than what
                    # we have in the database
                    effect_setting.value = new_value
                    session.commit()
                else:
                    log.debug(f'Value for {effect_setting.key} has not changed')

            log.debug(f"{found=}")
            change = False
            for effect_setting_key in self.traces:
                if effect_setting_key not in found:
                    change = True
                    log.debug(f'Expected key {effect_setting_key} does not exist in the database')
                    value = self.traces[effect_setting_key].get()
                    log.debug(f'Creating new EffectSetting({effect_id}, key={effect_setting_key}, value={value})')
                    new_setting = models.EffectSetting(
                        effect_id=effect_id,
                        key=effect_setting_key,
                        value=value
                    )
                    session.add(new_setting)

                if change:
                    session.commit()


    def load(self):
        """
        reflect the current db values for each effect setting
        to the tk.Variable tied to the widget for that
        setting.
        """

        effect_id = self.effect_id.get()
        log.debug(f'Loading {effect_id=}')

        with models.db() as session:
            effect_settings = session.scalars(
                select(models.EffectSetting).where(
                    models.EffectSetting.effect_id == effect_id
                )
            ).all()

            found = set()
            for setting in effect_settings:
                log.debug(f'Working on {setting}')
                
                if setting.key in found:
                    log.debug(f'Duplicate setting for {setting.key=} where {effect_id=}')
                    session.delete(setting)
                    continue

                found.add(setting.key)

                tkvar = getattr(self, setting.key, None)

                if setting.key not in self.traces:
                    if tkvar:
                        tkvar.set(setting.value)
                    else:
                        log.error(
                            f'Invalid configuration.  '
                            f'{setting.key} is not available for '
                            f'{self}')
                
                    tkvar.trace_add("write", self.reconfig)
                    self.traces[setting.key] = tkvar
            session.commit()

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
        log.debug('get_effect()')
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
            pname='frequency',
            label='Frequency (Hz)', 
            desc="Filter frequency in Hz",
            default=100,
            from_=100,
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
            pname='frequency',
            label='Frequency (Hz)', 
            desc="Filter frequency in Hz",
            default=100,
            from_=100,
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
        log.debug('get_effect()')
        effect = voicebox.effects.Glitch(
            chunk_time=self.chunk_time.get(),
            p_repeat=self.p_repeat.get(),
            max_repeats=int(self.max_repeats.get())
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
            default=0.0,
            from_=-1,
            to=1,
            digits=2,
            resolution=0.1
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


class PitchShift(EffectParameterEditor):
    label = "PitchShift"
    desc = "A pitch shifting effect that can change the pitch of audio without affecting its duration."

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="semitones",
            label='Semitones', 
            desc="How far to shift the pitch",
            default=0.5,
            from_=-8,
            to=8,
            digits=2,
            resolution=0.25
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.PitchShift(
                semitones=self.semitones.get(), 
            )
        )
        return effect


class Reverb(EffectParameterEditor):
    label = "Reverb"
    desc = (
        "A simple reverb effect. Uses a simple stereo reverb algorithm, based "
        "on the technique and tunings used in FreeVerb "
        "<https://ccrma.stanford.edu/~jos/pasp/Freeverb.html>_.  "
        "The delay lengths are optimized for a sample rate of 44100 Hz."
    )

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="room_size",
            label='Room size', 
            desc="Room Size",
            default=0.4,
            from_=0.05,
            to=1,
            digits=3,
            resolution=0.05
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="damping",
            label='Damping', 
            desc="damping parameter [0=low damping, 1=higher damping]",
            default=0.4,
            from_=0.05,
            to=1,
            digits=3,
            resolution=0.05
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="wet_level",
            label='Wet level', 
            desc="Wet Level",
            default=0.4,
            from_=0.05,
            to=1,
            digits=3,
            resolution=0.05
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="dry_level",
            label='Dry level', 
            desc="Dry Level",
            default=0.4,
            from_=0.05,
            to=1,
            digits=3,
            resolution=0.05
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="width",
            label='Width', 
            desc="width (left-right mixing) parameter",
            default=0.4,
            from_=0.05,
            to=1,
            digits=3,
            resolution=0.05
        ).pack(side='top', fill='x', expand=True)

        LBoolean(
            self,
            pname="freeze_mode",
            label='Freeze mode', 
            desc="frozen/unfrozen",
            default=False
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Reverb(
                room_size=self.room_size.get(), 
                damping=self.damping.get(), 
                wet_level=self.wet_level.get(),
                dry_level=self.dry_level.get(), 
                width=self.width.get(), 
                freeze_mode= 1 if self.freeze_mode.get() else 0
            )
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

        # The returned array may contain up to (but not more than) the same
        # number of samples as were provided. If fewer samples were returned
        # than expected, the plugin has likely buffered audio inside itself. To
        # receive the remaining audio, pass another audio buffer into process
        # with reset set to True.
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


class Delay(EffectParameterEditor):
    label = "Delay"
    desc = """A digital delay plugin with controllable delay time, feedback percentage, and dry/wet mix."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="delay_seconds",
            label='Delay (sec)', 
            desc="",
            default=0.25,
            from_=-0.1,
            to=0.5,
            digits=3,
            resolution=0.01
        ).pack(side='top', fill='x', expand=True)

        LScale(
            self,
            pname="feedback",
            label='Feedback (%)', 
            desc="",
            default=0.0,
            from_=0,
            to=1,
            digits=2,
            resolution=0.05
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

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Delay(
                delay_seconds=self.delay_seconds.get(), 
                feedback=self.feedback.get(),
                mix=self.mix.get(),
            )
        )
        return effect


class Distortion(EffectParameterEditor):
    label = "distortion"
    desc = """A distortion effect, which applies a non-linear (tanh, or hyperbolic tangent) waveshaping function to apply harmonically pleasing distortion to a signal."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="drive_db",
            label='Drive (db)', 
            desc="",
            default=25,
            from_=-1,
            to=50,
            digits=1,
            resolution=1
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Distortion(
                drive_db=self.drive_db.get(), 
            )
        )
        return effect


class Gain(EffectParameterEditor):
    label = "gain"
    desc = """A gain plugin that increases or decreases the volume of a signal by amplifying or attenuating it by the provided value (in decibels). No distortion or other effects are applied.
        Think of this as a volume control."""

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        LScale(
            self,
            pname="gain_db",
            label='Gain (db)', 
            desc="",
            default=1,
            from_=-1,
            to=20,
            digits=2,
            resolution=0.5
        ).pack(side='top', fill='x', expand=True)

    def get_effect(self):
        effect = voicebox.effects.PedalboardEffect(
            pedalboard.Gain(
                gain_db=self.gain_db.get(), 
            )
        )
        return effect


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
                cutoff_frequency_hz=self.cutoff_frequency_hz.get(),
                gain_db=self.gain_db.get(), 
                q=self.q.get()
            )
        )
        return effect


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
                cutoff_hz=self.cutoff_hz.get(), 
                resonance=self.resonance.get(),
                drive=self.drive.get()
            )
        )
        return effect


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
            resolution=1
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
            carrier_freq=self.carrier_freq.get(),
            blend=self.blend.get(),
            carrier_wave=getattr(np, self.carrier_wave.get())
        )
        return effect


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
            resolution=1
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
            carrier_freq=self.carrier_freq.get(),
            min_freq=self.min_freq.get(),
            max_freq=self.max_freq.get(),
            bands=self.bands.get(),
            bandwidth=self.bandwidth.get(),
            bandpass_filter_order=self.bandpass_filter_order.get()
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
    'Delay': Delay, # Pedalboard
    'Distortion': Distortion, # Pedalboard
    'Gain': Gain, # Pedalboard
    'Glitch': Glitch,
    # 'GSMFullRateCompressor': None, # Pedalboard
    'Highpass Filter': HighpassFilter,
    'HighShelfFilter': HighShelfFilter, # Pedalboard
    'LadderFilter': LadderFilter, # Pedalboard
    # 'Limiter': None, # Pedalboard
    'Lowpass Filter': LowpassFilter,
    # 'LowShelfFilter': None, # Pedalboard
    # 'MP3Compressor': None, # Pedalboard
    # 'NoiseGate': None, # Pedalboard
    'Normalize': Normalize,
    # 'PeakFilter': None, # Pedalboard
    # 'Phaser': None, # Pedalboard
    'PitchShift': PitchShift, # Pedalboard
    # 'Remove DC Offset': None,
    # 'Resample': None, # Pedalboard
    'Reverb': Reverb, # Pedalboard
    'RingMod': RingMod,
    'Vocoder': Vocoder,
}
