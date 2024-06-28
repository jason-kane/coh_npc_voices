
import logging
import os
import tkinter as tk
from tkinter import ttk

import cnv.lib.settings as settings
from cnv.engines import engines

log = logging.getLogger(__name__)


class ConfigurationTab(ttk.Frame):
    tkdict = {}

    def elevenlabs_token_frame(self):
        elevenlabs = ttk.Frame(
            self, 
            borderwidth=1, 
            relief="groove"
        )
        ttk.Label(
            elevenlabs,
            text="ElevenLabs API Token",
            anchor="e",
        ).pack(side="left", fill="x", expand=True)
        
        self.elevenlabs_key = tk.StringVar(value=self.get_elevenlabs_key())
        self.elevenlabs_key.trace_add('write', self.change_elevenlabs_key)
        ttk.Entry(
            elevenlabs,
            textvariable=self.elevenlabs_key,
            show="*"
        ).pack(side="left", fill="x", expand=True)
        return elevenlabs

    def polymorph(self, a, b, c):
        """
        Given a config change through the UI, persist it.  Easy.
        """
        log.warning('Polymorph is a dangerous and powerful thing')
        for key in self.tkdict:
            value = self.tkdict[key].get()
            # settings is smart enough to only write to disk when there is
            # a change so this is much better than worst case.
            settings.set_config_key(key, value)
        return

    def get_tkvar(self, tkvarClass, category, system, tag):
        """
        There is a tkvarClass instance located at category/system/tag.
        Instantiate it, give it the right value, hand it back.
        """
        key = f'{category}_{system}_{tag}'
        tkvar = self.tkdict.get(key)
        if tkvar is None:
            tkvar = tkvarClass(
                value=settings.get_config_key(key, False)  # False is sus.
            )
            tkvar.trace_add(
                'write', self.polymorph
            )
            self.tkdict[key] = tkvar

        return tkvar

    def normalize_prompt_frame(self, parent, category):
        """
        frame with ui for the normalize checkbox
        """
        frame = ttk.Frame(parent)
        ttk.Label(
            frame,
            text="Normalize all voices",
            anchor="e",
        ).grid(column=0, row=1)

        tk.Checkbutton(
            frame,
            variable=self.get_tkvar(tk.BooleanVar, category, 'engine', 'normalize')
        ).grid(column=1, row=1)
        return frame
              
    def engine_priorities_frame(self, category):
        """
        the whole config frame for a particular category of entity within the game.
        npc/player/system
        """
        frame = ttk.Frame(
            self,
            borderwidth=1, 
            relief="groove"
        )

        ttk.Label(
            frame,
            text=f"{category}",
            anchor="e",
        ).pack(side="top")

        primary_engine = self.choose_engine(
            frame,
            "Primary Engine",
            self.get_tkvar(tk.StringVar, category, 'engine', 'primary')
        )
        primary_engine.pack(side="top")

        secondary_engine = self.choose_engine(
            frame,
            "Secondary Engine",
            self.get_tkvar(tk.StringVar, category, 'engine', 'secondary')
        )
        secondary_engine.pack(side="top")

        # tkvar = self.get_tkvar(tk.BooleanVar, category, 'engine', 'normalize')
        self.normalize_prompt_frame(frame, category).pack(side="top")

        return frame

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.elevenlabs_token_frame().pack(side="top", fill="x")
       
        self.engine_priorities_frame("npc").pack(side="top", fill="x")
        self.engine_priorities_frame("player").pack(side="top", fill="x")
        self.engine_priorities_frame("system").pack(side="top", fill="x")
        
    def choose_engine(self, parent, prompt, engine_var):
        frame = ttk.Frame(
            parent, 
        )
        ttk.Label(
            frame,
            text=prompt,
            anchor="e",
        ).grid(column=0, row=0)

        default_engine_combo = ttk.Combobox(frame, textvariable=engine_var)
        default_engine_combo["values"] = [e.cosmetic for e in engines.ENGINE_LIST]
        default_engine_combo["state"] = "readonly"
        default_engine_combo.grid(column=1, row=0)

        return frame

    def change_elevenlabs_key(self, a, b, c):
        with open("eleven_labs.key", 'w') as h:
            h.write(self.elevenlabs_key.get())

    def get_elevenlabs_key(self):
        keyfile = 'eleven_labs.key'
        value = None

        if os.path.exists(keyfile):
            with open(keyfile, 'r') as h:
                value = h.read()
        return value

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
