

import tkinter as tk
from tkinter import ttk

import lib.settings as settings


class PowerAutoclick:
    def __init__(self, powername, vartype, default):
        self.name = powername
        self.key = f"auto_{self.name}"
        value = settings.get_config_key(self.key, default=default)
        self.var = getattr(tk, vartype)(value=value)
        self.listener()

    def listener(self):
        self.var.trace_add('write', lambda a,b,c:self.change_setting())

    def change_setting(self):
        value = self.var.get()
        settings.set_config_key(self.key, value)

    def widget(self, parent):
        return tk.Checkbutton(
            parent,
            variable=self.var
        )        


class AutomationTab(ttk.Frame):
    """
    Lets make this awesome.
    """

    def __init__(self, parent, event_queue, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        if parent:
            self.draw()

    def draw(self):
        for power in [ 
            PowerAutoclick('hasten', 'BooleanVar', False), 
            PowerAutoclick('domination', 'BooleanVar', False), 
        ]:
            frame = ttk.Frame(self)
            tk.Label(
                frame,
                text=f"Autoclick {power.name}",
            ).pack(side="left")

            mywidget = power.widget(frame)
            mywidget.pack(side='left')
            frame.pack(side="top")
