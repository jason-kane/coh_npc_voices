"""Hello World application for Tkinter"""

import logging
import multiprocessing
import os
import queue

import sys
import tkinter as tk
from tkinter import font, ttk

import db
import effects
import engines
import models

import voice_builder
import npc_chatter
from npc import PRESETS
from pedalboard.io import AudioFile
from sqlalchemy import delete, exc, select, update
from sqlalchemy.orm import Session
from voicebox.sinks import Distributor, SoundDevice, WaveFile

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("__name__")


class ChoosePhrase(tk.Frame):
    ALL_PHRASES = "< Rebuild all phrases >"
    def __init__(self, parent, detailside, selected_character, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.selected_character = selected_character
        self.detailside = detailside

        self.chosen_phrase = tk.StringVar(
            value="<Choose or type a phrase>"
        )
        self.options = ttk.Combobox(
            self, 
            textvariable=self.chosen_phrase
        )
        self.options["values"] = []

        self.populate_phrases()
        self.options.pack(side="left", fill="x", expand=True)

        play_btn = tk.Button(self, text="Play", command=self.say_it)
        play_btn.pack(side="left")

    def populate_phrases(self):
        raw_name = self.selected_character.get()
        try:
            category, name = raw_name.split(maxsplit=1)
        except ValueError:
            log.error('Invalid character raw_name: %s', raw_name)
            return

        with models.Session(models.engine) as session:            

            try:
                category = models.category_str2int(category)
            except ValueError:
                log.error('Invalid Character Category: %s', category)
                return
            
            character = session.scalars(
                select(models.Character).where(
                    models.Character.name == name,
                    models.Character.category == category,
                )
            ).first()

            if character is None:
                log.error(f'62 Character {category}|{name} does not exist!')
                return

            character_phrases = session.scalars(
                select(models.Phrases).where(
                    models.Phrases.character_id == character.id
                )
            ).all()
       
        if character_phrases:
            self.chosen_phrase.set(character_phrases[0].text)
        else:
            self.chosen_phrase.set(
                f'I have no record of what {raw_name} says.')
        self.options["values"] = [
            p.text for p in character_phrases
        ] + [ self.ALL_PHRASES ]

    def say_it(self):
        message = self.chosen_phrase.get()

        log.debug(f"Speak: {message}")
        # parent is the frame inside DetailSide
        engine_name = self.detailside.engineSelect.selected_engine.get()
        ttsengine = engines.get_engine(engine_name)
        log.info(f"Engine: {ttsengine}")

        effect_list = [
            e.get_effect() for e in self.detailside.effect_list.effects
        ]

        raw_name = self.selected_character.get()
        if not raw_name:
            log.warning('Name is required')
            return
        
        category, name = raw_name.split(maxsplit=1)

        with models.Session(models.engine) as session:
            character = session.scalars(
                select(models.Character).where(
                    models.Character.name == name,
                    models.Character.category == models.category_str2int(category)
                )
            ).first()

            all_phrases = [ 
                n.text for n in session.scalars(
                    select(models.Phrases).where(
                        models.Phrases.character_id == character.id
                    )
                ).all()
            ]

        if message == self.ALL_PHRASES:
            message = self.options["values"]
        else:
            message = [ message ]

        for msg in message:
            if msg == self.ALL_PHRASES:
                continue

            _, clean_name = db.clean_customer_name(character.name)
            filename = db.cache_filename(character.name, msg)
            log.debug(f'all_phrases: {all_phrases}')
            if msg in all_phrases:
                cachefile = os.path.abspath(
                    os.path.join(
                        "clip_library",
                        character.cat_str(),
                        clean_name,
                        filename
                    )
                )

                sink = Distributor([
                    SoundDevice(),
                    WaveFile(cachefile + '.wav')
                ])

                log.info(f'effect_list: {effect_list}')
                log.info(f"Creating ttsengine for {self.selected_character.get()}")
                # None because we aren't attaching any widgets
                ttsengine(None, self.selected_character).say(msg, effect_list, sink=sink)

                log.info('Converting to mp3...')
                with AudioFile(cachefile + ".wav") as input:
                    with AudioFile(
                        filename=cachefile, 
                        samplerate=input.samplerate,
                        num_channels=input.num_channels
                    ) as output:
                        while input.tell() < input.frames:
                            output.write(input.read(1024))
                        log.info(f'Wrote {cachefile}')
            else:
                # No Cache
                log.info(f'Bypassing filesystem caching ({msg})')
                ttsengine(None, self.selected_character).say(msg, effect_list)


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
        log.info('EngineSelectAndConfigure.chage_selected_engine()')
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
        log.info('EngineSelectAndConfig.save_character()')
        raw_name = self.selected_character.get()
        if not raw_name:
            log.warning('Name is required to save a character')
            return
        
        category, name = raw_name.split(maxsplit=1)
        engine_string = self.selected_engine.get()
        if engine_string in [None, ""]:
            engine_string = engines.default_engine

        with models.Session(models.engine) as session:
            
            character = session.scalars(
                select(models.Character).where(
                    models.Character.name == name,
                    models.Character.category == models.category_str2int(category)
                )
            ).first()

            if character.engine != engine_string:
                log.info(
                    'Saving changed engine_string (%s): %s -> %s', 
                    character.name,
                    character.engine, 
                    engine_string
                )
                character.engine = engine_string
                session.commit()

    def load_character(self):
        """
        We've set the character name, we want the rest of the metadata to
        populate.  Setting the engine name will domino the rest.
        """
        raw_name = self.selected_character.get()
        if raw_name in [None, ""]:
            log.error('Cannot load_character() with no character name.')
            return
        
        log.info(f'EngineSelectAndConfigure.load_character: {raw_name}!r')
        category, name = raw_name.split(maxsplit=1)

        with models.Session(models.engine) as session:
            character = session.scalars(
                select(models.Character).where(
                    models.Character.name==name,
                    models.Character.category==models.category_str2int(category)
                )
            ).first()

        if character is None:
            log.error(f'Character {name} does not exist.')
            return None
       
        if character.engine in ["", None]:
            self.selected_engine.set(engines.default_engine)
        else:
            self.selected_engine.set(character.engine)
            
        return character


class EffectList(tk.Frame):
    """

    """
    def __init__(self, parent, selected_character, *args, **kwargs):
        real_parent = parent.frame
        super().__init__(real_parent, *args, **kwargs)
        self.effects = []
        self.parent = real_parent
        self.detailside = parent
        self.buffer = False
        self.selected_character = selected_character
        self.load_effects()

    def load_effects(self):
        log.info('EffectList.load_effects()')
        has_effects = False

        # teardown any effects already in place
        while self.effects:
            effect = self.effects.pop()
            effect.clear_traces()
            effect.pack_forget()

        raw_name = self.selected_character.get()
        if raw_name in ["", None]:
            return

        category, name = raw_name.split(maxsplit=1)

        with models.Session(models.engine) as session:
            character = session.scalars(
                select(models.Character).where(
                    models.Character.name==name,
                    models.Character.category==models.category_str2int(category)
                )
            ).first()
            
            if character is None:
                log.error(
                    'Cannot load effects.  Character %s|%s does not exist.', 
                    category, name
                )
                return

            voice_effects = session.scalars(
                select(models.Effects).where(
                    models.Effects.character_id==character.id
                )
            ).all()

            for effect in voice_effects:
                has_effects = True
                log.info(f'Adding effect {effect} found in the database')
                effect_class = effects.EFFECTS[effect.effect_name]

                # not very DRY
                effect_config_frame = effect_class(
                    self, 
                    borderwidth=1, 
                    highlightbackground="black", 
                    relief="groove"
                )
                effect_config_frame.pack(side="top", fill="x", expand=True)
                effect_config_frame.effect_id.set(effect.id)
                self.effects.append(effect_config_frame)

                # we are not done yet.
                effect_settings = session.scalars(
                    select(models.EffectSetting).where(
                        models.EffectSetting.effect_id == effect.id
                    )
                ).all()

                for setting in effect_settings:

                    tkvar = getattr(effect_config_frame, setting.key, None)
                    if tkvar:
                        tkvar.set(setting.value)
                    else:
                        log.error(
                            f'Invalid configuration.  '
                            f'{setting.key} is not available for '
                            f'{effect_config_frame}')
                        
            #self.parent.pack(side="top", fill="x", expand=True)
            if not has_effects:
                self.buffer = tk.Frame(self, width=1, height=1).pack(side="top")
            else:
                if self.buffer:
                    self.buffer.pack_forget()

            if hasattr(self.detailside, "add_effect"):
                log.info("Rebuilding add_effect")
                self.detailside.add_effect.pack_forget()
                # .pack(side="top", fill="x", expand=True)
                self.detailside.add_effect = AddEffect(self.parent, self)
                self.detailside.add_effect.pack(side="top", fill='x', expand=True)
                # self.detailside.effect_list.pack(side="top", fill="x")
                # self.detailside.frame.pack(side="top", fill="x", expand=True)
                # self.detailside.canvas.pack(side="left", fill="both", expand=True)
                # self.detailside.pack(side="left", fill="both", expand=True)
                # self.detailside.parent.pack(side="top", fill="both", expand=True)
            else:
                log.info('DetailSide has no add_effect()')

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

            raw_name = self.selected_character.get()
            category, name = raw_name.split(maxsplit=1)

            with models.Session(models.engine) as session:
                # retrieve this character
                character = session.scalars(
                    select(models.Character).where(
                        models.Character.name==name,
                        models.Character.category==models.category_str2int(category)
                    )
                ).first()

                # save the current effect selection
                effect = models.Effects(
                    character_id=character.id,
                    effect_name=effect_name
                )
                session.add(effect)
                session.commit()
                session.refresh(effect)

            for key in effect_config_frame.parameters:
                # save the current effect configuration
                tkvar = getattr(effect_config_frame, key)
                value = tkvar.get()

                new_setting = models.EffectSetting(
                    effect_id=effect.id,
                    key=key,
                    value=value
                )
                session.add(new_setting)
            session.commit()
            
            effect_config_frame.effect_id.set(effect.id)      
    
    def remove_effect(self, effect_obj):
        log.info(f'Removing effect {effect_obj}')
        
        # remove it from the effects list
        self.effects.remove(effect_obj)
        
        # remove it from the database
        with models.Session(models.engine) as session:
            session.execute(
                delete(models.Effects).where(
                    models.Effects.id == effect_obj.effect_id.get()
                )
            )
            session.commit()

        # forget the widgets for this object
        effect_obj.pack_forget()
        self.pack()


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
        #effect_combobox.option_add('*TCombobox*Listbox.Justify', 'center')
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
        self.parent = parent
        self.selected_character = selected_character
        self.listside = None

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

        name_frame = tk.Frame(self.frame)

        self.character_name = tk.Label(
            name_frame,
            textvariable=selected_character,
            anchor="center",
            font=font.Font(weight="bold"),
        ).pack(side="left", fill="x", expand=True)

        tk.Button(
            name_frame,
            text="X",
            anchor="center",
            width=1,
            height=1,
            command=self.remove_character
        ).pack(side="right")

        name_frame.pack(side="top", fill="x", expand=True)

        self.phrase_selector = ChoosePhrase(
            self.frame, self, selected_character
        )
        self.phrase_selector.pack(side="top", fill="x", expand=True)

        self.presetSelect = PresetSelector(
            self.frame, self, self.selected_character
        )
        self.presetSelect.pack(side="top", fill="x", expand=True)

        self.engineSelect = EngineSelectAndConfigure(
            self.frame, self.selected_character
        )
        self.engineSelect.pack(side="top", fill="x", expand=True)

        # list of effects already configured
        self.effect_list = EffectList(self, selected_character)
        self.effect_list.pack(side="top", fill="x", expand=True)
        self.add_effect = AddEffect(self.frame, self.effect_list)
        self.add_effect.pack(side="top", fill="x", expand=True)

    def remove_character(self):
        #self.parent = parent
        # parent of detailside is 'editor', a Frame of root.
        # what we really need is listside, which is passed
        # a detailside -- maybe we can do this backwards.
        #
        #self.selected_character = selected_character        
        if self.listside:
            self.listside.delete_selected_character()

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
        log.info(f'DetailSide.load_character({raw_name})')
        raw_was = self.selected_character.get()
        if raw_was != raw_name:
            self.selected_character.set(raw_name)

        category, name = raw_name.split(maxsplit=1)
        
        with models.Session(models.engine) as session:
            character = session.scalars(
                select(models.Character).where(
                    name==name, 
                    category==category
                )
            ).first()

        # update the phrase selector
        self.phrase_selector.populate_phrases()

        # set the engine itself
        log.info('character: %s | %s', character, character.engine)
        self.engineSelect.set_engine(character.engine)

        # set engine and parameters
        self.engineSelect.engine_parameters.load_character(raw_name)
        
        # effects
        self.effect_list.load_effects()

        # reset the preset selector
        self.presetSelect.reset()

        # scroll to the top
        self.vsb.set(0, 1)
        self.canvas.yview_moveto(0)


class PresetSelector(tk.Frame):
    choose_a_preset = f"{'< Use a Preset >': ^70}"

    def __init__(self, parent, detailside, selected_character, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.selected_character = selected_character
        self.detailside = detailside
       
        self.chosen_preset = tk.StringVar(value=self.choose_a_preset)
        self.chosen_preset.trace_add("write", self.choose_preset)

        preset_combobox = ttk.Combobox(
            self,
            textvariable=self.chosen_preset
        )
        preset_combobox["values"] = list(PRESETS.keys())
        preset_combobox["state"] = "readonly"

        preset_combobox.pack(side="left", fill="x", expand=True)

    def reset(self):
        self.chosen_preset.set(self.choose_a_preset)

    def choose_preset(self, varname, lindex, operation):
        log.info('PresetSeelctor.choose_preset()')
        preset_name = self.chosen_preset.get()
        if preset_name == self.choose_a_preset:
            log.info('** No choice detected **')
            return

        raw_name = self.selected_character.get()
        category, name = raw_name.split(maxsplit=1)

        with models.Session(models.engine) as session:
            character = session.scalars(
                select(models.Character).where(
                    models.Character.name==name,
                    models.Character.category==models.category_str2int(category)
                )
            ).first()

        log.info(f'Applying preset {preset_name}')
        voice_builder.apply_preset(character, preset_name)

        self.detailside.load_character(self.selected_character.get())


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

        cursor = db.get_cursor()
        character_id, engine_name = cursor.execute(
            "SELECT id, engine FROM character WHERE name = ? AND category = ?", 
            (name, category)
        ).fetchone()
        cursor.close()

        return cls(id=character_id, name=name, engine=engine_name, category=category)

    def __str__(self) -> str:
        return f"{self.category} {self.name}"
    
    def get_phrases(self):
        """
        Return a list of all the phrases this character has previously spoken
        """
        cursor = db.get_cursor()
        phrases = [
            phrase[0] for phrase in cursor.execute("""
                SELECT text FROM phrases WHERE character_id = ?
            """, (self.id, )).fetchall()
        ]
        cursor.close()
        return phrases

class ListSide(tk.Frame):
    def __init__(self, parent, detailside, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.detailside = detailside
        #wait, what?
        self.detailside.listside = self

        self.list_items = tk.Variable(value=[])
        self.refresh_character_list()

        self.listbox = tk.Listbox(self, height=10, listvariable=self.list_items)
        self.listbox.pack(side="top", expand=True, fill=tk.BOTH)

        action_frame = tk.Frame(self)
        tk.Button(
            action_frame,
            text="Refresh",
            command=self.refresh_character_list
        ).pack(
            side="right"
        )

        action_frame.pack(side="top", expand=False, fill=tk.X)
        self.listbox.select_set(0)
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
        log.info('Refreshing Character list from the database...')

        with models.Session(models.engine) as session:
            all_characters = session.scalars(
                select(models.Character).order_by(models.Character.name)
            ).all()

        if all_characters:
            self.list_items.set(
                [f"{character.cat_str()} {character.name}" for character in all_characters]
            )
    
    def delete_selected_character(self):
        index = int(self.listbox.curselection()[0])
        raw_name = self.listbox.get(index)
        log.info(f'Deleting character {raw_name!r}')

        category, name = raw_name.split(maxsplit=1)
        log.info(f'Name: {name!r}  Category: {category!r}')
        with models.Session(models.engine) as session:
            try:
                session.execute(
                    delete(models.Character)
                    .where(
                        models.Character.name == name,
                        models.Character.category == models.category_str2int(category)
                    )
                )
                session.commit()

            except Exception as err:
                log.error(f'DB Error: {err}')
                raise

        # dude, delete everything they have ever said from
        # disk too.

        self.refresh_character_list()
        self.listbox.select_clear(0, 'end')
        self.listbox.select_set(0)
        self.listbox.event_generate("<<ListboxSelect>>")


class ChatterService:
    def start(self, event_queue):
        speaking_queue = queue.Queue()

        npc_chatter.TightTTS(speaking_queue, event_queue)
        speaking_queue.put((None, "Attaching to most recent log...", 'system'))

        logdir = "G:/CoH/homecoming/accounts/VVonder/Logs"
        #logdir = "g:/CoH/homecoming/accounts/VVonder/Logs"
        badges = True
        team = True
        npc = True

        ls = npc_chatter.LogStream(
            logdir, speaking_queue, event_queue, badges, npc, team
        )
        while True:
            ls.tail()


class Chatter(tk.Frame):
    attach_label = 'Attach to Log'
    detach_label = "Detach from Log"

    def __init__(self, parent, event_queue, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.event_queue = event_queue
        self.button_text = tk.StringVar(value=self.attach_label)
        self.attached = False
        self.hero = None

        settings = models.get_settings()
        
        self.logdir = tk.StringVar(value=settings.logdir)
        self.logdir.trace_add('write', self.save_logdir)

        tk.Button(
            self, 
            textvariable=self.button_text, 
            command=self.attach_chatter
        ).pack(
            side="left"
        )
        tk.Entry(
            self, 
            textvariable=self.logdir
        ).pack(
            side="left",
            fill='x',
            expand=True
        )
         
        tk.Button(
            self,
            text="Set Log Dir",
            command=self.ask_directory
        ).pack(side="left")
        
        self.cs = ChatterService()

    def save_logdir(self, *args):
        logdir = self.logdir.get()
        log.info(f'Persisting setting logdir={logdir} to the database...')
        with models.Session(models.engine) as session:
            session.execute(
                update(models.Settings).values(
                    logdir=logdir
                )
            )
            session.commit()

    def ask_directory(self):
        dirname = tk.filedialog.askdirectory()
        self.logdir.set(dirname)

    def attach_chatter(self):
        """
        Not sure exactly how I want to do this.  I think the best long term
        option is to just launch a process and be done with it.
        """
        if self.attached:
            # we are already attached, I guess we want to stop.
            self.p.terminate()
            self.button_text.set(self.attach_label)
            self.attached = False
            log.info('Detached')
        else:
            # we are not attached, lets do that.
            self.attached = True
            self.button_text.set(self.detach_label)
            self.p = multiprocessing.Process(target=self.cs.start, args=(self.event_queue, ))
            self.p.start()
            log.info('Attached')


def main():
    root = tk.Tk()
    # root.iconbitmap("myIcon.ico")
    root.geometry("640x480+200+200")
    root.resizable(True, True)
    root.title("Character Voice Editor")

    chatter = Chatter(root, None)
    chatter.pack(side="top", fill="x")

    editor = tk.Frame(root)
    editor.pack(side="top", fill="both", expand=True)

    cursor = db.get_cursor()
    first_character = cursor.execute("select id, name, category from character order by name").fetchone()
    cursor.close()

    if first_character:
        selected_character = tk.StringVar(value=f"{first_character[2]} {first_character[1]}")
    else:
        selected_character = tk.StringVar()

    detailside = DetailSide(editor, selected_character)
    listside = ListSide(editor, detailside)

    listside.pack(side="left", fill="x", expand=True)
    detailside.pack(side="left", fill="x", expand=True)

    root.mainloop()


if __name__ == '__main__':
    if sys.platform.startswith('win'):
        multiprocessing.freeze_support()
    main()

# TODO (eta: weeks)
# ----

# Release Blockers
#######################
# friendly installer/uninstaller
#     py2exe?
#        doesn't work with 3.12
#     pyinstaller?
#        can't get multiprocessing to work :(  it spawns a whole
#        new editor when you attach.
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
# some mechanism to update/refresh the character list when new entries are added
# effects are not removed when you change between npc
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
