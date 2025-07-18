
import logging
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
import cnv.lib.settings as settings
from cnv.engines.base import registry as engine_registry

log = logging.getLogger(__name__)

# so this can be a whole good thing.  We need to figure out how the translate
# apis work on our various engines the we can make this work and not be so
# ridiculously terrible.

class SpokenLanguageSelection(ctk.CTkFrame):
    """
    The user gets to decide which language they want to hear.  They may also
    need to decide which translation provider to utilize w/config for that
    provider.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.columnconfigure(0, minsize=125, uniform="baseconfig")
        self.columnconfigure(1, weight=2, uniform="baseconfig")

        ctk.CTkLabel(
            self,
            text="Spoken Language",
            anchor="e",   
        ).grid(column=0, row=0, sticky='e')

        current = settings.get_config_key('language', "English")
        self.language = tk.StringVar(value=current)

        default_engine_combo = ctk.CTkComboBox(
            self, 
            variable=self.language,
            state='readonly',
            values=list(settings.LANGUAGES.keys())
        )
        default_engine_combo.grid(column=1, row=0, sticky='w')

        self.language.trace_add('write', self.change_language)
       
    def change_language(self, a, b, c):
        newvalue = self.language.get()
        prior = settings.get_config_key('language', "English")
        settings.set_config_key('language', newvalue)
        # tempting to just restart
        if prior and newvalue != prior:
            log.info(f'Changing language to {newvalue}')
            # we should immediately translate and localize the UI       


class TranslationTab(tk.Frame):
  
    def __init__(self, parent, event_queue, speaking_queue, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        SpokenLanguageSelection(self).pack(side="top", fill="x")
