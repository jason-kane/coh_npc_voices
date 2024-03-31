"""Hello World application for Tkinter"""

import tkinter as tk
from tkinter import ttk, font
import os
import logging
import sys
import effects
import engines
import voice_builder
from db import get_cursor, commit, prepare_database


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("__name__")


class ChoosePhrase(tk.Frame):
    def __init__(self, parent, detailside, selected_character, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.selected_character = selected_character
        self.detailside = detailside

        self.chosen_phrase = tk.StringVar(value="<Choose or type a phrase>")
        self.options = ttk.Combobox(self, textvariable=self.chosen_phrase)
        self.options["values"] = []

        self.populate_phrases()
        self.options.pack(side="left", fill="x", expand=True)

        play_btn = tk.Button(self, text="Play", command=self.say_it)
        play_btn.pack(side="left")

    def populate_phrases(self):
        character = Character.get_by_raw_name(self.selected_character.get())
        if character is None:
            return
        log.info(character)
        
        character_phrases = character.get_phrases()
        
        if character_phrases:
            self.chosen_phrase.set(character_phrases[0])
        else:
            self.chosen_phrase.set(f'I have no record of what {self.selected_character.get()} says.')
        self.options["values"] = character_phrases

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
        ttsengine(None, self.selected_character).say(message, effect_list)


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

    def __init__(self, parent, selected_character, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.selected_character = selected_character

        self.selected_engine = tk.StringVar()
        self.load_character()

        self.selected_engine.trace_add(
            "write", 
            self.change_selected_engine
        )
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
        if engine_cls:
            self.engine_parameters = engine_cls(self, self.selected_character)
            self.engine_parameters.pack(side="top", fill="x", expand=True)

        self.save_character()

    def save_character(self):
        """
        save this engine selection to the database
        """
        cursor = get_cursor()
        full_name = self.selected_character.get()
        if not full_name:
            return

        category, name = full_name.split(maxsplit=1)
        cursor.execute(
            "UPDATE character SET engine = ? where name = ? and category = ?",
            (self.selected_engine.get(), name, category),
        )

        commit()
        log.debug(
            f"Saved engine={self.selected_engine.get()} for {category} named {name}"
        )

    def load_character(self):
        cursor = get_cursor()
        full_name = self.selected_character.get()
        if not full_name:
            log.warning('Name is required to load a character')
            return
        
        category, name = full_name.split(maxsplit=1)
        engine_name = cursor.execute(
            "SELECT engine FROM character WHERE name = ? AND category = ?", (name, category)
        ).fetchone()

        if engine_name:
            self.selected_engine.set(engine_name[0])
        else:
            self.selected_engine.set(engines.default_engine)


class EffectList(tk.Frame):
    """

    """
    def __init__(self, parent, selected_character, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.effects = []
        self.parent = parent
        self.selected_character = selected_character
        self.load_effects()

    def load_effects(self):
        log.info('EffectList.load_effects()')
        cursor = get_cursor()
        character = Character.get_by_raw_name(self.selected_character.get())

        voice_effects = cursor.execute("""
            SELECT 
                id, effect_name
            FROM
                effects
            where
                character_id = ?
        """, (
            character.id,
        )).fetchall()

        for effect in voice_effects:
            log.info(f'Adding effect {effect} found in the database')
            id, effect_name = effect
            effect_class = effects.EFFECTS[effect_name]

            # not very DRY
            effect_config_frame = effect_class(
                self, 
                borderwidth=1, 
                highlightbackground="black", 
                relief="groove"
            )
            effect_config_frame.pack(side="top", fill="x", expand=True)
            effect_config_frame.effect_id.set(id)
            self.effects.append(effect_config_frame)

            # we are not done yet.
            effect_setting = cursor.execute("""
                SELECT 
                    key, value
                FROM
                    effect_setting
                where
                    effect_id = ?
            """, (
                id,
            )).fetchall()

            for key, value in effect_setting:
                tkvar = getattr(effect_config_frame, key)
                tkvar.set(value)

    def add_effect(self, effect_name):
        """
        Add the chosen effect to the list of effects the user can manipulate.

        effect name is the nice, button friendly string.  Using it as the
        index for effects.EFFECTS is a bit dirty.  The button should have a
        companion value other than the label, the we can just use that as an
        index.

        This call is for new effects which will start with default configurations.
        """
        effect = effects.EFFECTS[effect_name]
        
        # effect is one of the EffectParameterEditor objects in effects.py
        if effect:
            #
            # effect_config_frame is an instance of one of the
            # EffectParameterEditor objects in effects.py.  They inherit
            # from tk.Frame. 
            #
            # Instantiating these objects creates any tk objects they need to
            # configure themselves and the tk.Frame returned can then be
            # pack/grid whatever to arrange the screen.
            # 
            # When we go to render we expect each effect to provide a
            # get_effect(self) that returns an Effect: 
            #   https://github.com/austin-bowen/voicebox/blob/main/src/voicebox/effects/effect.py#L9
            # with an apply(Audio) that returns an Audio; An "Audio" is a pretty
            # simple object wrapping a np.ndarray of [-1 to 1] samples.
            #
            effect_config_frame = effect(
                self, 
                borderwidth=1, 
                highlightbackground="black", 
                relief="groove"
            )
            effect_config_frame.pack(side="top", fill="x", expand=True)
            self.effects.append(effect_config_frame)

            character = Character.get_by_raw_name(self.selected_character.get())

            # persist this change to the database
            log.info(f'Saving new effect {effect_name} to database')
            cursor = get_cursor()
            cursor.execute("""
                INSERT 
                    INTO effects (character_id, effect_name)
                VALUES
                    (:character_id, :effect_name)
            """, {
                'character_id': character.id,
                'effect_name': effect_name
            })
            effect_id = cursor.lastrowid

            for key in effect_config_frame.parameters:
                tkvar = getattr(effect_config_frame, key)
                value = tkvar.get()

                cursor.execute("""
                    INSERT 
                        INTO effect_setting (effect_id, key, value)
                    VALUES
                        (:effect_id, :key, :value)
                """, {
                    'effect_id': effect_id,
                    'key': key,
                    'value': value
                })

            commit()
            effect_config_frame.effect_id.set(effect_id)
        
    
    def remove_effect(self, effect_obj):
        log.info(f'Removing effect {effect_obj}')
        
        # remove it from the effects list
        self.effects.remove(effect_obj)
        
        # remove it from the database
        cursor = get_cursor()
        cursor.execute("""
            DELETE
                FROM effects
            WHERE
                id=?
            """, (effect_obj.effect_id.get(), )
        )
        commit()
        # forget the widgets for this object
        effect_obj.pack_forget()


class AddEffect(tk.Frame):
    # where is this 70 coming from?  you got it from where?  what the
    # hell buddy.  This is the shit that causing errors when people
    # use an app at different resolutions.  This will center at one spot
    # and all the other entries will be different.
    add_an_effect = f"{'< Add an Effect >': ^70}"  # pad to center

    def __init__(self, parent, effect_list, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.effect_list = effect_list

        # we're using the textvariable as the action associated with changing
        # this combobox.  That only gives us the scope of what can see this
        # selected_effect to either read the current value or trace_add to 
        # trigger whenever selected_effect is written to.
        
        self.selected_effect = tk.StringVar(value=self.add_an_effect)
        self.selected_effect.trace_add("write", self.add_effect)

        effect_combobox = ttk.Combobox(
            self,
            textvariable=self.selected_effect
        )
        effect_combobox.option_add('*TCombobox*Listbox.Justify', 'center')
        effect_combobox["values"] = list(effects.EFFECTS.keys())
        effect_combobox["state"] = "readonly"

        #  <-[XXX    ]
        effect_combobox.pack(side="left", fill="x", expand=True)

        #  [XXX]->
        # tk.Button(self, text="Add Effect", command=self.add_effect).pack(side="right")

    def add_effect(self, varname, lindex, operation):
        # Retrieve the currently selected effect from the
        # tk.StringVar.
        effect_name = self.selected_effect.get()
        # effect_list provides a very handy helper to make this easy.  Our
        # output is just providing this effect_list[] for anyone that wants it.
        # Sounds kind of stupid when you actually type it out.
        self.effect_list.add_effect(effect_name)
               
        # reset the UI back to the "add an effect" prompt
        self.selected_effect.set(self.add_an_effect)



class DetailSide(tk.Frame):
    """
    Primary frame for the "detail" side of the application.
    """
    def __init__(self, parent, selected_character, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.selected_character = selected_character

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

        self.character_name = tk.Label(
            self.frame,
            textvariable=selected_character,
            anchor="center",
            font=font.Font(weight="bold"),
        ).pack(side="top", fill="x", expand=True)

        self.phrase_selector = ChoosePhrase(
            self.frame, self, selected_character
        )
        self.phrase_selector.pack(side="top", fill="x", expand=True)

        self.engineSelect = EngineSelectAndConfigure(
            self.frame, self.selected_character
        )
        self.engineSelect.pack(side="top", fill="x", expand=True)

        # list of effects already configured
        self.effect_list = EffectList(self.frame, selected_character)
        self.effect_list.pack(side="top", fill="both", expand=True)
        AddEffect(self.frame, self.effect_list).pack(side="top", fill="x", expand=True)

    def onFrameConfigure(self, event):
        """Reset the scroll region to encompass the inner frame"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def load_character(self, raw_name):
        """
        load this NPC and populate the detailside widgets
        """
        # set the engine
        # set engine parameters
        # loop effects
        # add each effect
        # set parameters for each effect
        log.debug(f'load_character({raw_name})')
        self.selected_character.set(raw_name)

        category, name = raw_name.split(maxsplit=1)

        cursor = get_cursor()
        character_id, engine_name = cursor.execute(
            "SELECT id, engine FROM character WHERE name = ? AND category = ?", 
            (name, category)
        ).fetchone()

        # update the phrase selector
        self.phrase_selector.populate_phrases()

        # set the engine itself
        self.engineSelect.set_engine(engine_name)

        # set engine and parameters
        self.engineSelect.engine_parameters.load_character(raw_name)
        return


class Character:
    def __init__(self, id, name, engine, category):
        self.id = id
        self.name = name
        self.category = category
    
    @classmethod
    def get_by_raw_name(cls, raw_name):
        if not raw_name:
            return None

        category, name = raw_name.split(maxsplit=1)

        cursor = get_cursor()
        character_id, engine_name = cursor.execute(
            "SELECT id, engine FROM character WHERE name = ? AND category = ?", 
            (name, category)
        ).fetchone()

        return cls(id=character_id, name=name, engine=engine_name, category=category)

    def __str__(self) -> str:
        return f"{self.category} {self.name}"
    
    def get_phrases(self):
        """
        Return a list of all the phrases this character has previously spoken
        """
        cursor = get_cursor()
        return [
            phrase[0] for phrase in cursor.execute("""
                SELECT text FROM phrases WHERE character_id = ?
            """, (self.id, )).fetchall()
        ]        

class ListSide(tk.Frame):
    def __init__(self, parent, detailside, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.detailside = detailside

        self.list_items = tk.Variable(value=[])
        self.refresh_character_list()

        self.listbox = tk.Listbox(self, height=10, listvariable=self.list_items)
        self.listbox.pack(side="top", expand=True, fill=tk.BOTH)

        self.listbox.bind("<<ListboxSelect>>", self.character_selected)

    def character_selected(self, event=None):
        if len(self.listbox.curselection()) == 0:
            # we de-selected everything
            # TODO: wipe the detail side?
            return

        index = int(self.listbox.curselection()[0])
        value = self.listbox.get(index)

        self.detailside.load_character(value)

    def refresh_character_list(self):
        cursor = get_cursor()
        all_characters = cursor.execute("select id, name, category from character order by name").fetchall()
        if all_characters:
            self.list_items.set([f"{character[2]} {character[1]}" for character in all_characters])


def main():
    prepare_database()
    root = tk.Tk()
    root.geometry("640x480+300+300")
    root.resizable(False, False)
    root.title("Character Voice Editor")

    cursor = get_cursor()
    first_character = cursor.execute("select id, name, category from character order by name").fetchone()

    if first_character:
        selected_character = tk.StringVar(value=f"{first_character[2]} {first_character[1]}")
    else:
        selected_character = tk.StringVar()

    detailside = DetailSide(root, selected_character)
    listside = ListSide(root, detailside)

    listside.pack(side="left", fill="both", expand=True)
    detailside.pack(side="left", fill="both", expand=True)

    root.mainloop()


main()

# TODO (eta: weeks)
# ----

# Research
##########
# Can I use pedalboard for reading/writing mp3 files?

# Release Blockers
#######################
# friendly installer/uninstaller
# effects are not removed when you change between npc
# more effects

# Not-blocking Glitches
#######################
# logging is weird.. debug isn't coming through and I'm not sure why
# in-app update of app software
# in-app update of voice database
# when you edit an NPC, option to rebuild everything they say with the new 
#     settings saving the mp3 to the file system (same as cache)
# right side does not fill the width
# no mechanism to remove NPCs
# mouse-scroll doesn't move right side scrollbar
# removing effects does not repack

# DONE
# ----
# persist effects to database
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
