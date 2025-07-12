import logging
import tkinter as tk

import customtkinter as ctk
from sqlalchemy import select

import cnv.database.models as models
from cnv.lib.gui import Feather

log = logging.getLogger(__name__)

# scipy iir filters
IIR_FILTERS = ['butter', 'cheby1', 'cheby2', 'ellip', 'bessel']

# how long can effect description be before the text wraps
WRAPLENGTH=350

IGNORE_SETTING = ['blend', ]

class EffectRegistry:
    def __init__(self):
        self.effects = {}

    def add_effect(self, cosmetic, effect_parameter_editor):
        log.debug(f'Registering plugin: {cosmetic}')
        self.effects[cosmetic] = effect_parameter_editor

    def get_effect(self, key):
        return self.effects[key]

    def effect_list(self):
        return sorted(list(self.effects.keys()))

    def get_effects(self):
        return self.effects
    
    def count(self):
        return len(self.effects)


registry = EffectRegistry()


class LScale(ctk.CTkFrame):
    """
    Labeled choose-a-number
    """
    def __init__(
        self,
        parent,
        pname,    # property name: "threshold_db"
        label,    # cosmetic: "Threshold (db)"
        desc,     # ""
        default,  # initial value: 0.0
        from_,    # left-most value:  -10
        to,       # right-most value:  10
        _type=float,
        *args, 
        digits=None, #  how many numbers after the . should we display
        resolution: float=0.0,  #  Distance between 'notches' in scale: 0.5 
        **kwargs
    ):
        super().__init__(parent, *args, **kwargs)
        self.columnconfigure(0, minsize=125, uniform="effect")
        self.columnconfigure(1, weight=2, uniform="effect")
        
        if isinstance(_type, int) or digits==0:
            parent.tkvars[pname] = tk.IntVar(
                name=f"{parent.label.lower()}_{pname}",
                value=default
            )
        else:
            parent.tkvars[pname] = tk.DoubleVar(
                name=f"{parent.label.lower()}_{pname}",
                value=default
            )

        parent.display_tkvars[pname] = tk.StringVar(
            name=f"{parent.label.lower()}_{pname}_display",
            value=str(default)
        )

        if digits is not None:
            # parent is the frame, digits is a friendly dict it uses to let anyone 
            # passing by to override the number of digits displayed.
            parent.digits[pname] = digits

        # label for the setting
        ctk.CTkLabel(
            self,
            text=label,
            anchor="e",
            justify='right'
        ).grid(row=0, column=0, sticky='e', padx=5)

        # TODO:
        # mark ticks/steps?
        if resolution:
            steps = (to - from_) / resolution
        else:
            steps = 20
        
        if steps > 100:
            highest_recommended = (to - from_) / 100
            log.warning(f'[{parent.label}] Resolution {resolution} for {label} is too detailed.  Maybe {highest_recommended}?')

        # widget for changing the value
        ctk.CTkSlider(
            self,
            variable=parent.tkvars[pname],
            from_=from_,
            to=to,
            orientation='horizontal',
            number_of_steps=steps
        ).grid(row=0, column=1, sticky='ew')

        # label for the current value
        ctk.CTkLabel(
            self,
            textvariable=parent.display_tkvars[pname]
        ).grid(row=0, column=2, sticky='e')


class LCombo(ctk.CTkFrame):
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

        parent.tkvars[pname] = tk.StringVar(value=default)
        self.columnconfigure(0, minsize=125, uniform="effect")
        self.columnconfigure(1, weight=2, uniform="effect")

        # label for the setting
        ctk.CTkLabel(
            self,
            text=label,
            anchor="e",
            justify='right'
        ).grid(row=0, column=0, sticky='e')

        # widget for viewing/changing the value
        options = ctk.CTkComboBox(
            self, 
            values=list(choices),
            variable=parent.tkvars[pname],
            state='readonly'
        )
            
        options.grid(row=0, column=1, sticky='ew')


class LBoolean(ctk.CTkFrame):
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

        self.columnconfigure(0, minsize=125, uniform="effect")
        self.columnconfigure(1, weight=2, uniform="effect")

        parent.tkvars[pname] = tk.BooleanVar(
            name=f"{pname}",
            value=default
        )

        # label for the setting
        ctk.CTkLabel(
            self,
            text=label,
            anchor="e",
            justify='right'
        ).grid(row=0, column=0, sticky='e')

        # widget for viewing/changing the value
        ctk.CTkSwitch(
            self, 
            text="",
            variable=parent.tkvars[pname],
            onvalue=True,
            offvalue=False
        ).grid(row=0, column=1, sticky='ew')


class EffectParameterEditor(ctk.CTkFrame):
    label = "Label"
    desc = "Description of effect"

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        # parent is the effectlist, it allows us to remove ourselves.
        self.parent = parent  
        
        # database id for this unique, configured effect (why is this a tk.?)
        self.effect_id = tk.IntVar()
               
        # tk.var for each parameter
        self.tkvars = {}

        # tk.var for how the value of each parameter should be displayed
        self.display_tkvars = {}

        # storage bucket for tkVar traces for each parameter
        self.traces = {}

        # how many digits should we display after the decimal point?        
        self.digits = {}

        # delete icon
        self.trashcan = Feather(
            'trash-2',
            size=22
        )

        topbar = ctk.CTkFrame(self)
        # the name of this effect
        ctk.CTkLabel(
            topbar,
            text=self.label.title() + " ",
            anchor="n",
            font=ctk.CTkFont(
                size=24,
                # weight="bold",
                slant='italic'
            )
        ).pack(side='left', fill='x', expand=True)
    
        # delete button
        ctk.CTkButton(
            topbar,
            image=self.trashcan.CTkImage,
            text="",
            width=40,
            command=self.remove_effect
        ).place(relx=1, rely=0, anchor='ne')

        topbar.pack(side="top", fill='x', expand=True)

        # the descriptive text for this effect
        ctk.CTkLabel(
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

            found = set()
            for effect_setting in effect_settings:
                # backward compatability is a bit of an after though.
                if effect_setting.key in IGNORE_SETTING:
                    continue

                log.debug(f'Sync to db {effect_setting}')
                found.add(effect_setting.key)
                try:
                    new_value = self.tkvars[effect_setting.key].get()
                    
                    if effect_setting.key in self.digits:
                        formatted_value = self.cosmetic(effect_setting.key, new_value)
                        log.debug(f'Setting widget to {formatted_value} (!= {new_value})')
                        self.display_tkvars[effect_setting.key].set(formatted_value)
                    else:
                        log.debug(f'{effect_setting.key} not in digits {self.digits}')
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

    def cosmetic(self, key, value):
        digits = self.digits.get(key, None)
        formatstr = "{:.%sf}" % digits
        formatted_value = formatstr.format(float(value))
        return formatted_value

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
                if setting.key in IGNORE_SETTING:
                    continue

                log.debug(f'Working on {setting}')
                
                if setting.key in found:
                    log.debug(f'Duplicate setting for {setting.key=} where {effect_id=}')
                    session.delete(setting)
                    continue

                found.add(setting.key)

                tkvar = self.tkvars.get(setting.key, None)

                if setting.key not in self.traces:
                    if tkvar:
                        tkvar.set(setting.value)
                        if setting.key in self.digits:
                            formatted_string = self.cosmetic(setting.key, setting.value)
                            self.display_tkvars[setting.key].set(formatted_string)

                        tkvar.trace_add("write", self.reconfig)
                        self.traces[setting.key] = tkvar
                    else:
                        log.error(
                            f'Invalid configuration.  '
                            f'{setting.key} is not available for '
                            f'{self}')
                
            session.commit()
