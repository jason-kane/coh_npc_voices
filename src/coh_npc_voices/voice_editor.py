"""Hello World application for Tkinter"""

import tkinter as tk
from tkinter import ttk, font
import sqlite3
import os
import logging
import sys
import effects
import engines
import voice_builder


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("__name__")


def prepare_database():
    if not os.path.exists("voices.db"):
        # first time with the database
        log.info("Initializing new database")
        con = sqlite3.connect("voices.db")
        cursor = con.cursor()
        cursor.execute("CREATE TABLE settings(dbversion)")
        cursor.execute("INSERT INTO settings VALUES(:version)", {"version": "0.1"})
        con.commit()
    else:
        con = sqlite3.connect("voices.db")
        cursor = con.cursor()

    dbversion = cursor.execute("select dbversion from settings").fetchone()[0]
    log.info(f"Database is version {dbversion}")
    if dbversion == "0.1":
        log.info("migrating to db schema 0.2")
        cursor.execute("UPDATE settings SET dbversion = '0.2'")
        # base NPC table, one row per npc name
        cursor.execute("""
            CREATE TABLE npc (
                id INTEGER PRIMARY KEY, 
                name VARCHAR(64) NOT NULL,
                engine VARCHAR(64) NOT NULL
            )""")

        # base engine configuration settings, things like language and voice
        # these settings are in the context of a specific NPC.  Exactly which
        # settings make sense depend on the engine, hence the key/value generic.
        cursor.execute("""
            CREATE TABLE base_tts_config (
                id INTEGER PRIMARY KEY,
                npc_id INTEGER NOT NULL,
                key VARCHAR(64),
                value VARCHAR(64)
            )
        """)
        cursor.execute("""
            CREATE TABLE google_voices (
                id INTEGER PRIMARY KEY,
                name VARCHAR(64) NOT NULL,
                language_code VARCHAR(64) NOT NULL,
                ssml_gender VARCHAR(64) NOT NULL
            )""")
        cursor.execute("""
            CREATE TABLE phrases (
                id INTEGER PRIMARY KEY,
                npc_id INTEGER NOT NULL,
                text VARCHAR(256)
            )
        """)
        con.commit()


class ChoosePhrase(tk.Frame):
    def __init__(self, parent, con, detailside, selected_npc, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.selected_npc = selected_npc
        self.con = con
        self.detailside = detailside

        self.chosen_phrase = tk.StringVar(value="<Choose or type a phrase>")
        self.options = ttk.Combobox(self, textvariable=self.chosen_phrase)
        self.options["values"] = []

        self.populate_phrases()
        self.options.pack(side="left", fill="x", expand=True)

        play_btn = tk.Button(self, text="Play", command=self.say_it)
        play_btn.pack(side="left")

    def populate_phrases(self):
        cursor = self.con.cursor()
        npc = engines.get_npc_by_name(cursor, self.selected_npc.get())
        if npc is None:
            return
        
        npc_id, _, engine = npc
        npc_phrases = [
            phrase[0] for phrase in cursor.execute("""
                SELECT text FROM phrases WHERE npc_id = ?
            """, (npc_id, )).fetchall()
        ]
        if npc_phrases:
            self.chosen_phrase.set(npc_phrases[0])
        else:
            self.chosen_phrase.set(f'I have no record of what {self.selected_npc.get()} says.')
        self.options["values"] = npc_phrases

    def say_it(self):
        message = self.chosen_phrase.get()
        log.debug(f"Speak: {message}")
        # parent is the frame inside DetailSide
        engine_name = self.detailside.engineSelect.selected_engine.get()
        ttsengine = engines.get_engine(engine_name)
        log.debug(f"Engine: {ttsengine}")

        effect_list = [e.get_effect() for e in self.detailside.effect_list.effects]
        # None because we aren't attaching any widgets
        log.info(f'effect_list: {effect_list}')
        ttsengine(None, self.con, self.selected_npc).say(message, effect_list)



class EngineSelection(tk.Frame):
    """
    Frame for just the Text to speech labal and
    a combobox to choose a different engine.  We are
    tracing on the variable, not binding the widget.
    """

    def __init__(self, parent, selected_engine, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.selected_engine = selected_engine
        tk.Label(self, text="Text to Speech Engine", anchor="e").pack(
            side="left", fill="x", expand=True
        )

        base_tts = ttk.Combobox(self, textvariable=self.selected_engine)
        base_tts["values"] = [e.cosmetic for e in engines.ENGINE_LIST]
        base_tts["state"] = "readonly"
        base_tts.pack(side="left", fill="x", expand=True)


class EngineSelectAndConfigure(tk.Frame):
    """
    two element stack, the first has the engine selection,
    the second has all the parameters supported by the seleted engine
    """

    def __init__(self, parent, con, selected_npc, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.con = con
        self.selected_npc = selected_npc

        self.selected_engine = tk.StringVar()
        self.load_npc()

        self.selected_engine.trace_add("write", self.change_selected_engine)
        es = EngineSelection(self, self.selected_engine)
        es.pack(side="top", fill="x", expand=True)
        self.engine_parameters = None
        self.change_selected_engine("", "", "")

    def set_engine(self, engine_name):
        self.selected_engine.set(engine_name)

    def change_selected_engine(self, a, b, c):
        """
        the user changed the engine.
        """
        # No problem.
        # clear the old engine configuration
        # show the selected engine configuration
        if self.engine_parameters:
            self.engine_parameters.pack_forget()

        engine_cls = engines.get_engine(self.selected_engine.get())

        self.engine_parameters = engine_cls(self, self.con, self.selected_npc)
        self.engine_parameters.pack(side="top", fill="x", expand=True)

        self.save_npc()

    def save_npc(self):
        """
        save this engine selection to the database
        """
        cursor = self.con.cursor()
        cursor.execute(
            "UPDATE npc SET engine = ? where name = ?",
            (self.selected_engine.get(), self.selected_npc.get()),
        )
        self.con.commit()
        log.debug(
            f"Saved engine={self.selected_engine.get()} for NPC named {self.selected_npc.get()}"
        )

    def load_npc(self):
        cursor = self.con.cursor()
        engine_name = cursor.execute(
            "SELECT engine FROM npc WHERE name = ?", (self.selected_npc.get(),)
        ).fetchone()

        if engine_name:
            self.selected_engine.set(engine_name[0])
        else:
            self.selected_engine.set(engines.default_engine)


class EffectList(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.effects = []
        self.parent = parent

    def add_effect(self, effect_name):
        effect = effects.EFFECTS[effect_name]

        if "obj" in effect:
            obj = effect["obj"](
                self, borderwidth=1, highlightbackground="black", relief="groove"
            )
            obj.pack(side="top", fill="x", expand=True)
            self.effects.append(obj)
    
    def remove_effect(self, effect_obj):
        log.info(f'Removing effect {effect_obj}')
        self.effects.remove(effect_obj)
        effect_obj.pack_forget()
        # effect_obj.destroy()
        # re-pack our parent
        #self.parent.pack(side="top", fill="both", expand=True)


class AddEffect(tk.Frame):
    def __init__(self, parent, effect_list, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.effect_list = effect_list

        self.selected_effect = tk.StringVar(value="<Choose an Effect>")
        self.options = ttk.Combobox(self, textvariable=self.selected_effect)
        self.options["values"] = list(effects.get_effects().keys())
        self.options["state"] = "readonly"

        self.options.pack(side="left", fill="x", expand=True)

        tk.Button(self, text="Add Effect", command=self.add_effect).pack(side="right")

    def add_effect(self):
        effect_name = self.selected_effect.get()
        self.effect_list.add_effect(effect_name)


class DetailSide(tk.Frame):
    def __init__(self, parent, con, selected_npc, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.con = con
        self.selected_npc = selected_npc

        self.canvas = tk.Canvas(self, borderwidth=0, background="#ffffff")
        self.frame = tk.Frame(self.canvas, background="#ffffff")
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.frame_id = self.canvas.create_window(
            (0, 0), window=self.frame, anchor="nw", tags="self.frame"
        )
        self.frame.bind("<Configure>", self.onFrameConfigure)
        # self.frame.pack(side='top', fill='x')

        self.npc_name = tk.Label(
            self.frame,
            textvariable=selected_npc,
            anchor="center",
            font=font.Font(weight="bold"),
        ).pack(side="top", fill="x", expand=True)

        self.phrase_selector = ChoosePhrase(
            self.frame, con, self, selected_npc
        )
        self.phrase_selector.pack(side="top", fill="x", expand=True)

        self.engineSelect = EngineSelectAndConfigure(
            self.frame, self.con, self.selected_npc
        )
        self.engineSelect.pack(side="top", fill="x", expand=True)

        # list of effects already configured
        self.effect_list = EffectList(self.frame)
        self.effect_list.pack(side="top", fill="both", expand=True)
        AddEffect(self.frame, self.effect_list).pack(side="top", fill="x", expand=True)

    def onFrameConfigure(self, event):
        """Reset the scroll region to encompass the inner frame"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def load_npc(self, name):
        """
        load this NPC and populate the detailside widgets
        """
        # set the engine
        # set engine parameters
        # loop effects
        # add each effect
        # set parameters for each effect
        self.selected_npc.set(name)

        cursor = self.con.cursor()
        npc_id, engine_name = cursor.execute(
            "SELECT id, engine FROM npc WHERE name = ?", (name,)
        ).fetchone()

        # update the phrase selector
        self.phrase_selector.populate_phrases()

        # set the engine itself
        self.engineSelect.set_engine(engine_name)

        # set engine and parameters
        self.engineSelect.engine_parameters.load_npc(npc_id)
        return


class ListSide(tk.Frame):
    def __init__(self, parent, con, detailside, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.con = con
        self.detailside = detailside

        self.list_items = tk.Variable(value=[])
        self.refresh_npc_list()

        self.listbox = tk.Listbox(self, height=10, listvariable=self.list_items)
        self.listbox.pack(side="top", expand=True, fill=tk.BOTH)

        self.listbox.bind("<<ListboxSelect>>", self.npc_selected)

        new_npc_frame = tk.Frame(self)
        self.new_entry = tk.Entry(new_npc_frame)
        self.new_entry.pack(side="left", expand=True, fill=tk.X)

        tk.Button(new_npc_frame, text="Add NPC", command=self.add_npc).pack(side="left")
        new_npc_frame.pack(side="top", fill=tk.X)

    def npc_selected(self, event=None):
        if len(self.listbox.curselection()) == 0:
            # we de-selected everything
            return

        index = int(self.listbox.curselection()[0])
        value = self.listbox.get(index)

        self.detailside.load_npc(value)

    def refresh_npc_list(self):
        cursor = self.con.cursor()
        all_npcs = cursor.execute("select id, name from npc order by name").fetchall()
        if all_npcs:
            self.list_items.set([npc[1] for npc in all_npcs])

    def add_npc(self):
        cursor = self.con.cursor()
        name = self.new_entry.get()
        cursor.execute(
            "INSERT INTO npc (name, engine) VALUES (:name, :engine);",
            {"name": name, "engine": voice_builder.default_engine},
        )
        self.con.commit()
        # npc = cursor.lastrowid
        # create default engine config here?
        self.listbox.insert(0, name)

        # select this list item, since it is now
        # the first item this is pretty easy.
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(0)


def main():
    prepare_database()

    con = sqlite3.connect("voices.db")
    cursor = con.cursor()

    root = tk.Tk()
    root.geometry("640x480+300+300")
    root.resizable(False, False)
    root.title("Character Voice Editor")

    first_npc = cursor.execute("select id, name from npc order by name").fetchone()

    if first_npc:
        selected_npc = tk.StringVar(value=first_npc[1])
    else:
        selected_npc = tk.StringVar()

    detailside = DetailSide(root, con, selected_npc)
    listside = ListSide(root, con, detailside)

    listside.pack(side="left", fill="both", expand=True)
    detailside.pack(side="left", fill="both", expand=True)

    root.mainloop()


main()

# TODO (eta: weeks)
# ----

# when you edit an NPC, option to rebuild everything they say with the new settings saving the mp3 to the file system
#
# persist effects to database
# right side does not fill the width
# no mechanism to remove NPCs
# mouse-scroll doesn't move right side scrollbar
# removing effects does not repack
# effects are not removed when you change between npc

# DONE
# ----
# no mechanism to remove effects
# add the things NPCs actually say to the DB, use those to populate 'Play' in the editor
# NPC list isn't populated
# choosing an NPC doesn't load that npc in the detail side
# changes on the right side do not persist to sqlite
# engine parameters are not filled in
# Only google text-to-speech works
# only Bandpass filter and Glitch effects work
# npc list should be populated from ncp_voices
# engine paramters options are not API populated
