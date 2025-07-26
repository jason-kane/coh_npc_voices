
import logging
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
import hashlib
import cnv.lib.settings as settings
from cnv.engines.base import registry as engine_registry

log = logging.getLogger(__name__)


class MasterVolume(ctk.CTkFrame):
    """
    Frame to provide widgets and persistence logic for a global volume control.  
    This is for playback volume.
    """

class EngineAuthentication(ctk.CTkTabview):
    """
    Collects tabs for configuring authentication for each of the TTS engines.  The 
    actual tab contents are provided by the engine(s).
    """

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        for _, engine_ui in engine_registry.engine_list():
            if engine_ui.auth_ui_class:
                                
                tab = self.add(name=engine_ui.auth_ui_class.label)
                panel = engine_ui.auth_ui_class(tab)
                panel.pack(fill="both", expand=True)
                

class ChannelToEngineMap(ctk.CTkFrame):
    """
    Allows the user to choose a primary and secondary for each channel.  _Current_ channels are
    npc, player and system.
    """
    tkdict = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.engine_priorities_header().pack(side="top", fill="x")
        for channel in ['npc', 'player', 'system']:
            self.engine_priorities_frame(channel).pack(side="top", fill="x")
              
    def engine_priorities_header(self):
        frame = ctk.CTkFrame(self)
        frame.columnconfigure(0, minsize=125, uniform="enginemap")
        frame.columnconfigure(1, weight=2, uniform="enginemap")
        frame.columnconfigure(2, weight=2, uniform="enginemap")
        frame.columnconfigure(3, weight=2, uniform="enginemap")

        for index, label in enumerate([
            '',
            'Primary Engine',
            'Secondary Engine',
            'Normalize Voices',
        ]):
            ctk.CTkLabel(
                frame,
                text=label,
                anchor="n",
            ).grid(column=index, row=0, sticky='n')
        
        return frame      

    def engine_priorities_frame(self, category):
        """
        the whole config frame for a particular category of entity within the game.
        npc/player/system
        """
        frame = ctk.CTkFrame(self)

        frame.columnconfigure(0, minsize=125, uniform="enginemap")
        frame.columnconfigure(1, weight=2, uniform="enginemap")
        frame.columnconfigure(2, weight=2, uniform="enginemap")
        frame.columnconfigure(3, weight=2, uniform="enginemap")

        ctk.CTkLabel(
            frame,
            text=f"{category}",
            anchor="e",
        ).grid(column=0, row=0, sticky='e')

        primary_engine = self.choose_engine(
            frame,
            self.get_tkvar(tk.StringVar, category, 'engine', 'primary', default='Disabled')
        )
        primary_engine.grid(column=1, row=0, sticky='n')

        secondary_engine = self.choose_engine(
            frame,
            self.get_tkvar(tk.StringVar, category, 'engine', 'secondary', default='Disabled')
        )
        secondary_engine.grid(column=2, row=0, sticky='n')

        self.normalize_prompt_frame(
            frame, category
        ).grid(column=3, row=0, sticky='n')

        return frame

    def polymorph(self, a, b, c):
        """
        Given a config change through the UI, persist it.  Easy.
        """
        for key in self.tkdict:
            value = self.tkdict[key].get()
            # settings is smart enough to only write to disk when there is
            # a change so this is much better than worst case.
            settings.set_config_key(key, value)
        return

    def get_tkvar(self, tkvarClass, category, system, tag, default: str | bool = False):
        """
        There is a tkvarClass instance located at category/system/tag.
        Instantiate it, give it the right value, hand it back.
        """
        key = f'{category}_{system}_{tag}'
        tkvar = self.tkdict.get(key)
        if tkvar is None:
            tkvar = tkvarClass(
                value=settings.get_config_key(key, default)  # False is sus.
            )
            tkvar.trace_add(
                'write', self.polymorph
            )
            self.tkdict[key] = tkvar

        return tkvar
        
    def choose_engine(self, parent, engine_var):
        frame = ctk.CTkFrame(parent)

        default_engine_combo = ctk.CTkComboBox(
            frame, 
            variable=engine_var,
            state='readonly',
            values=[e.cosmetic for (_, e) in engine_registry.engine_list()]
        )
        default_engine_combo.grid(column=1, row=0)

        return frame

    # WTF do you think you are doing!?!  What is this shit?
    def change_default_engine(self, a, b, c):
        settings.set_config_key(
            'DEFAULT_ENGINE',
            self.default_engine.get()
        )

    def change_default_engine_normalize(self, a, b, c):
        settings.set_config_key(
            'DEFAULT_ENGINE_NORMALIZE',
            self.default_engine_normalize.get()
        )

    def change_default_player_engine(self, a, b, c):
        settings.set_config_key(
            'DEFAULT_PLAYER_ENGINE',
            self.default_player_engine.get()
        )        

    def change_default_player_engine_normalize(self, a, b, c):
        settings.set_config_key(
            'DEFAULT_PLAYER_ENGINE_NORMALIZE',
            self.default_player_engine_normalize.get()
        )

    def normalize_prompt_frame(self, parent, category):
        """
        frame with ui for per-channel configuration of the normalize feature
        """
        frame = ctk.CTkFrame(parent)

        ctk.CTkCheckBox(
            frame,
            text='',
            variable=self.get_tkvar(tk.BooleanVar, category, 'engine', 'normalize')
        ).grid(column=0, row=0, sticky='n')
        return frame


class SpeakingToggles(ctk.CTkFrame):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.toggles = {}

        index = 0
        # so the _idea_ is, by making it easy to add these toggles, it will be
        # easy to let users opt in/opt out of different types of generated audio
        # because tastes differ.  
        # TODO: We are missing a default state, so these have to be phrased to
        # the default false which is dumb. 

        # IMPORTANT 

        # ie: I want the initial default for the "Acknowledge each win" audio to
        # be true because I think it's a better experience.  But because the
        # default must be false to get the desired result, I have to rephrase it
        # as "Igmore each win" or "Victories are beneith your notice".
        # 
        #  I can't do it right now though, becase I'm doing something else and
        #  it would be a distraction.
        for toggle in [
            "Acknowledge each win", 
            "Persist player chat",
            "Speak Buffs",
            "Speak Debuffs",
        ]:
            tag = settings.taggify(toggle)
            self.toggles[tag] = tk.StringVar(
                value="on" if settings.get_toggle(tag) else "off"
            )

            ctk.CTkCheckBox(
                self,
                command=self.toggle,
                text=toggle,
                variable=self.toggles[tag],
                onvalue="on", 
                offvalue="off"
            ).grid(column=0, row=index, sticky='w')

            index += 1

    def toggle(self, *args, **kwargs):
        for tag in self.toggles:
            value = self.toggles[tag].get()
            log.info(f"{tag} {value}")
            settings.set_toggle(tag, value)
        return


class DirectoryChoices(ctk.CTkFrame):

    def save_config(self, *args):
        logdir = self.logdir.get()
        clip_library_dir = self.clip_library_dir.get()
        
        log.debug(f'Persisting setting {logdir=};{clip_library_dir=}')
        settings.set_config_key('logdir', logdir)
        settings.set_config_key('clip_library_dir', clip_library_dir)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logdir = tk.StringVar(
            value=settings.get_config_key('logdir', default='')
        )
        # too much magic?  when you change the stringvar, it saves the new value to the config file.
        self.logdir.trace_add(
            'write', 
            lambda var_name, index, mode: settings.set_config_key('logdir', self.logdir.get())
        )

        self.clip_library_dir = tk.StringVar(
            value=settings.get_config_key('clip_library_dir', default='')
        )
        # self.clip_library_dir.trace_add('write', self.save_config)
        self.clip_library_dir.trace_add(
            'write', 
            lambda var_name, index, mode: settings.set_config_key('clip_library_dir', self.clip_library_dir.get())
        )
        
        # wide directory name display
        self.columnconfigure(1, weight=4)
        
        # short button
        self.columnconfigure(2, weight=1)

        ctk.CTkEntry(
            self, 
            textvariable=self.logdir
        ).grid(column=1, row=0, sticky="ew")
         
        ctk.CTkButton(
            self,
            text="COH Log Dir",
            command=lambda: self.logdir.set(tk.filedialog.askdirectory())
        ).grid(column=2, row=0, sticky="w")

        ctk.CTkEntry(
            self, 
            textvariable=self.clip_library_dir
        ).grid(column=1, row=1, sticky="ew")
         
        ctk.CTkButton(
            self,
            text="Set Clip Library Dir",
            command=lambda: self.clip_library_dir.set(tk.filedialog.askdirectory())
        ).grid(column=2, row=1, sticky="w")


class ConfigurationTab(tk.Frame):
  
    def __init__(self, parent, event_queue, speaking_queue, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        
        # MasterVolume(self).pack(side="top", fill="x")
        DirectoryChoices(self).pack(side="top", fill="x")

        ChannelToEngineMap(self).pack(side="top", fill="x")
        SpeakingToggles(self).pack(side="top", fill="x")
        EngineAuthentication(
            self,
        ).pack(side="top", fill="x")
        