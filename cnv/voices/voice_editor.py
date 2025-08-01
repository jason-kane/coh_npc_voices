"""Voice Editor component"""
import logging
import os
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from pygame import mixer
from scipy.io import wavfile
from sqlalchemy import delete, desc, select
from translate import Translator
from voicebox.sinks import Distributor, SoundDevice, WaveFile

from cnv.database import db, models
from cnv.effects import registry
from cnv.engines.base import USE_SECONDARY
from cnv.engines import registry as engine_registry
from cnv.lib import settings
from cnv.lib.gui import Feather

log = logging.getLogger(__name__)
ENGINE_OVERRIDE = {}



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


class WavfileMajorFrame(ctk.CTkFrame):    
    ALL_PHRASES = "⪡  Rebuild all phrases  ⪢"
    
    def __init__(self, rank, *args, **kwargs):
        log.debug(f"Initializing WavfileMajorFrame({rank=})")
        # kwargs['text'] = 'Wavefile(s)'
        super().__init__(*args, **kwargs)
        self.phrase_id = []
        self.rank = rank
        # self.visualize_wav = None
        
        self.fig = None
        self.plt = None
        self.spec = None
        self.canvas = None

        frame = ctk.CTkFrame(self)
        
        self.translated = tk.StringVar(value="")

        self.chosen_phrase = tk.StringVar(
            value="<Choose or type a phrase>"
        )
        self.chosen_phrase.trace_add('write', self.choose_phrase)
        self.options = ctk.CTkComboBox(
            frame, 
            values=[],
            variable=self.chosen_phrase
        )
        self.options.pack(side="left", fill="x", expand=True)

        self.play_btn = ctk.CTkButton(
            frame, 
            text="Play", 
            width=80, 
            command=self.play_cache
        )

        regen_btn = ctk.CTkButton(
            frame, text="Regen", width=80, command=self.say_it
        )
        regen_btn.pack(side="left")
        self.play_btn.pack(side="left")

        frame.pack(side="top", expand=True, fill="x")

        # NOT inside the frame
        ctk.CTkLabel(
            self,
            textvariable=self.translated,
            wraplength=350,
            anchor="nw",
            justify="left"
        ).pack(side="top", fill="x")    

        # Wavfile visualizations
        self.visualize_wav = ctk.CTkFrame(self)

        mixer.init()

        # must be called after self.play_btn exists
        self.populate_phrases()

    def set_translated(self, *args, **kwargs):
        """
        The translated string has changed, display it in
        the user interface.
        TODO
        """
        return

    def choose_phrase(self, *args, **kwargs):
        """
        a phrase was chosen.
        """
        # make sure this characters is the one selected in the character list
        character = models.get_selected_character()
        
        # retrieve the selected phrase
        message = self.options.get()
        if message in [self.ALL_PHRASES, ]:
            return

        # determine the id of this phrase
        phrase = models.get_or_create_phrase(
            character.name,
            character.category,
            message
        )
        
        # we want to work with the translated string
        message, is_translated = models.get_translated(phrase.id)

        if is_translated:
            self.translated.set(message)
        else:
            self.translated.set("")

        # find the file associated with this phrase
        cachefile = self.get_cachefile(
            character, message, self.rank
        )

        if os.path.exists(cachefile + ".wav"):
            # activate the play button and display the waveform
            #wavfilename = audio.mp3file_to_wavfile(
            #    mp3filename=cachefile
            #)
            self.play_btn.configure(state="normal")
            # and display the wav
            self.show_wave(cachefile + ".wav")
            return
    
        log.debug(f'{cachefile}.wav does not exist.')
        self.clear_wave()
        self.play_btn.configure(state="disabled")

    def populate_phrases(self):
        log.debug('** populate_phrases() called **')
        
        try:
            character = models.get_selected_character()
        except models.NoCharacterSelected:
            # no character selected
            return 

        # pull phrases for this character from the database
        with models.db() as session:
            character_phrases = session.scalars(
                select(models.Phrases).where(
                    models.Phrases.character_id == character.id
                )
            ).all()

        values = []
        self.phrase_id = []
        for phrase in character_phrases:
            self.phrase_id.append(phrase.id)
            values.append(phrase.text)
        
        values.append(self.ALL_PHRASES)
        self.options.configure(values=values)

        if character_phrases:
            # default to the first phrase
            self.chosen_phrase.set(character_phrases[0].text)
            
            message, is_translated = models.get_translated(
                self.phrase_id[0]
            )

            if is_translated:
                self.translated.set(message)
            else:
                self.translated.set("")
        else:
            self.chosen_phrase.set(
                f'I have no record of what {character.name} says.')
            self.translated.set("")

    def clear_wave(self):
        if hasattr(self, 'canvas'):
            log.debug('*** clear_wave() called ***')
            if self.plt:
                self.plt.clear()

            if self.spec:
                self.spec.clear()
            
            if self.canvas:
                #for item in self.canvas.get_tk_widget().find_all():
                #    self.canvas.get_tk_widget().delete(item)
    
                self.canvas.draw_idle()

    def show_wave(self, cachefile):
        """
        Visualize a wav file

        I know, not very efficient to just jam this in here
        * https://learnpython.com/blog/plot-waveform-in-python/
        * https://matplotlib.org/3.1.0/gallery/user_interfaces/embedding_in_tk_sgskip.html        
        """
        if self.fig is None:
            self.fig = Figure(
                figsize=(3, 4), # (width, height) figsize in inches (not kidding)
                dpi=100, # but we get dpi too so... sane?
                layout='constrained'
            )

        if self.plt is None:
            self.plt = self.fig.add_subplot(211, facecolor=('xkcd:light grey'))
        else:
            self.plt.remove()
            self.plt = self.fig.add_subplot(211, facecolor=('xkcd:light grey'))

        if self.spec is None:
            self.spec = self.fig.add_subplot(212)
        else:
            self.spec.clear()

        # 211 = rows=2 columns=1 index=1
        if self.canvas is None:
            self.canvas = FigureCanvasTkAgg(self.fig, self.visualize_wav)
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=1)

        sampling_rate, data = wavfile.read(cachefile)
        
        log.debug(f'*** show_wave({cachefile=}) called ***')

        # if channels == 1:
        self.plt.plot(data)
        self.spec.specgram(data, Fs=sampling_rate)
        self.canvas.draw_idle()

        # elif channels == 2:
        #     self.plt.plot(times, l_channel, label="Left Channel")
        #     self.plt.plot(times, r_channel, label="Right Channel")

        # self.plt.set_xlim(0, duration)
        self.visualize_wav.pack(side='top', fill=tk.BOTH, expand=1)

    def get_cachefile(self, character: models.Character, msg, rank):
        log.debug(f'Determining cachefile name for {character} {msg} {rank}')
        _, clean_name = settings.clean_customer_name(character.name)
        filename = settings.cache_filename(character.name, msg, rank)
        
        return os.path.join(
            settings.clip_library_dir(),
            character.cat_str(),
            clean_name,
            filename
        )
 
    def play_cache(self):
        """
        Play the cachefile
        """
        global ENGINE_OVERRIDE
        message = self.chosen_phrase.get()
        
        character = models.get_selected_character()

        if message == self.ALL_PHRASES:
            with models.db() as session:
                # every phrase this character has ever said previously.  These make it
                # easy to tune the voice with the same dialog.
                all_phrases = session.scalars(
                    select(models.Phrases).where(
                        models.Phrases.character_id == character.id
                    )
                ).all()
        else:
            phrase = models.get_or_create_phrase(
                name=character.name,
                category=character.category,
                message=message
            )
            all_phrases = [ phrase, ]

        for phrase in all_phrases:
            msg, is_translated = models.get_translated(phrase.id)
            cachefile = self.get_cachefile(character, msg, self.rank)

            # wavfilename = audio.mp3file_to_wavfile(
            #     mp3filename=cachefile
            # )
            wavfilename = cachefile + ".wav"
            self.show_wave(wavfilename)
            
            log.info(f'Playing {wavfilename}')
            mixer.Sound(file=wavfilename).play()
            
    def say_it(self, use_secondary=False):
        """
        Speak aloud whatever is in the chosen_phrase tk.Variable, using whatever
        TTS engine is selected.

        doing this with the selected value instead of the db value for the current
        character was a bad idea.  sorry.
        """
        global ENGINE_OVERRIDE
        message = self.chosen_phrase.get()    

        log.debug(f"Speak: {message}")
        
        engine_name = models.get_engine(self.rank)
        ttsengine = engine_registry.get_engine(engine_name)
        log.debug(f"Engine: {ttsengine}")

        effect_list = [
            e.get_effect() for e in models.get_effects()
        ]

        character = models.get_selected_character()
        
        if message == self.ALL_PHRASES:
            with models.db() as session:
                # every phrase this character has ever said previously.  These make it
                # easy to tune the voice with the same dialog.
                all_phrases = session.scalars(
                        select(models.Phrases).where(
                            models.Phrases.character_id == character.id
                        )
                    ).all()
        else:
            all_phrases = [ models.get_or_create_phrase(
                name=character.name,
                category=character.category,
                message=message
            ), ]

        msg = ""  # in case all_phrases is empty
        for phrase in all_phrases:
            if phrase.text in ["", ]:
                continue

            log.debug(f'{phrase=}')

            # this is an existing phrase
            # is there an existing translation?
            msg, is_translated = models.get_translated(phrase.id)
            
            cachefile = settings.get_cachefile(
                character.name,
                msg,
                character.cat_str(),
                rank=self.rank
            )

            sink = Distributor([
                SoundDevice(),
                WaveFile(cachefile + '.wav')
            ])

            # make sure the destination directory exists
            os.makedirs(os.path.dirname(cachefile), exist_ok=True)

            log.debug(f'effect_list: {effect_list}')
            log.debug(f"Creating ttsengine for {character.name}")

            # None because we aren't attaching any widgets
            try: 
                log.debug(f'{ttsengine}(None, {self.rank}, name={character.name}, category={character.category}).say(msg, effect_list, sink={sink})')
                ttsengine(None, self.rank, name=character.name, category=character.category).say(msg, effect_list, sink=sink)
            except USE_SECONDARY:
                return
                    
            self.show_wave(cachefile + ".wav")

            # why?
            # cachefile = audio.wavfile_to_mp3file(
            #     wavfilename=cachefile + ".wav",
            #     mp3filename=cachefile + ".mp3"
            # )
            
            self.play_btn["state"] = "normal"

        if not all_phrases:
            # this isn't an existing phrase
            # No Cache
            log.debug(f'Bypassing filesystem caching ({msg})')
            language = settings.get_language_code()

            if language != "en":
                log.debug(f'Translating "{msg}" into {language}')
                translator = Translator(to_lang=language)
                msg = translator.translate(msg)

            #try:
            ttsengine(None, self.rank, character.name, character.category).say(msg, effect_list)
            # except engines.DISABLE_ENGINES:
            #     # I'm not even sure what we want to do.  The user clicked 'play' but
            #     # we don't have any quota left for the selected engine.
            #     # lets go dumb-simple.
            #     tk.messagebox.showerror(title="Error", message=f"Engine {engine_name} did not provide audio")


class EngineSelectAndConfigure(ctk.CTkFrame):
    """
    Responsible for everything inside the "Engine" section
    of the detailside.  There is one instance of this object per
    layer of engine (primary, secondary, etc..)
    """
    def __init__(self, rank, *args, **kwargs):
        super().__init__(*args, **kwargs)
        log.debug(f'EngineSelectAndConfigure.__init__({rank=}')
        self.rank = rank
        self.engine_parameters = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        #-- Row 0 --------------------------------------
        speech_engine_selection = ctk.CTkFrame(self)

        speech_engine_selection.columnconfigure(0, minsize=125, weight=0, uniform="ttsengine")
        speech_engine_selection.columnconfigure(1, weight=2, uniform="ttsengine")
        
        ctk.CTkLabel(speech_engine_selection, text="Speech Engine", anchor="e").grid(
            row=0, column=0, sticky="e", padx=10
        )

        self.selected_engine = tk.StringVar()
        self.selected_engine.trace_add(
            "write", 
            self.change_selected_engine
        )

        # doing this by cosmetic is so icky.
        # TODO: figure out how to do that in ctk
        base_tts = ctk.CTkComboBox(
            speech_engine_selection, 
            variable=self.selected_engine,
            state='readonly',
            values=[e.cosmetic for (_, e) in engine_registry.engine_list()]
        )

        base_tts.grid(
            column=1, row=0, sticky="new"
        )
        speech_engine_selection.grid(
            column=0, row=0, sticky="new"
        )
        #########################################
        # end of row 0
        
        # gap for engine parameters.  load_character_engines will
        # call set_engine which will fill this in.

        # start of row 2
        self.engine_parameters = None           
        self.phrase_selector = WavfileMajorFrame(
            self.rank, self
        )
        self.phrase_selector.grid(
            columnspan=2, column=0, row=2, sticky="new"
        )

        with models.Session(models.engine) as session:
            self.load_character_engines(session)      

    def set_engine(self, engine_name):
        """
        When a character is loading (detailside.load_character()) this is
        called.  We can expect models.get_selected_character() to provide
        a character object for whomever we are working on.
        """
        log.debug(f'[{self.rank}] ESC.set_engine({engine_name})')

        # this set() will trip change_selected_engine
        # which will in turn set a value for engine_parameters
        self.selected_engine.set(engine_name)  

    def change_selected_engine(self, a, b, c):
        """
        1. the user changed the engine for this character. 
         
        or 
        
        2. we swapped the character out from under this, then did an engine.set
        which is triggered here to configure a totally different character.

        Having this one function handle both those states is a poor design,
        since only state #1 should write anything to the database.
        """
        # No problem.
        # clear the old engine configuration
        # show the selected engine configuration
        log.debug('EngineSelectAndConfigure.change_selected_engine()')
        
        character = models.get_selected_character()
        engine_name = self.selected_engine.get()
        log.debug('{engine_name=} {character=}')
        if not engine_name:
            return

        clear = False

        if character is None:
            return

        if self.rank == "primary":
            if character.engine != engine_name:
                clear = True
                log.debug(f'{self.rank} engine changing from {character.engine!r} to {engine_name!r}')
        elif self.rank == "secondary":
            if character.engine_secondary != engine_name:
                clear = True
                log.debug(f'{self.rank} engine changing from {character.engine_secondary!r} to {engine_name!r}')

        if self.engine_parameters:
            log.debug('Clearing prior engine_parameters')
            children = self.engine_parameters.winfo_children()
            for w in children:
                w.destroy()
            self.engine_parameters.destroy()

        # remove any existing engine level configuration
        if clear:
            log.debug(f'Deleting BaseTTS for {character.id=} {self.rank=}')
            with models.db() as session:
                rows = session.scalars(
                    select(models.BaseTTSConfig).where(
                        models.BaseTTSConfig.character_id == character.id,
                        models.BaseTTSConfig.rank == self.rank
                    )
                ).all()

                for row in rows:
                    log.debug(f'Deleting {row}...')
                    session.delete(row)
                session.commit()
        else:
            log.debug(f'Not changing the {self.rank} character engines ({engine_name})')

        models.set_engine(self.rank, engine_name)
        engine_cls = engine_registry.get_engine(engine_name)

        if not engine_cls:
            # that didn't work.. try the default engine
            log.warning(f'Invalid Engine: {engine_name!r}.  Using default {settings.DEFAULT_ENGINE} engine.')
            engine_cls = engine_registry.get_engine(settings.DEFAULT_ENGINE)

        self.engine_parameters = engine_cls(
            self,
            rank=self.rank, 
            category=character.category,
            name=character.name
        )
        self.engine_parameters.grid(column=0, row=1, columnspan=2, sticky='new')
        
        # update the phrase selector
        self.phrase_selector.populate_phrases()

        self.save_character()

    def save_character(self):
        """
        save this engine selection to the database
        """
        log.debug('EngineSelectAndConfig.save_character()')
        character = models.get_selected_character()
       
        category_str = models.category_int2str(character.category)
        name = character.name

        engine_string = self.selected_engine.get()
        if engine_string in [None, ""]:
            if category_str == "player":
                engine_string = settings.get_config_key(
                    'DEFAULT_ENGINE', settings.DEFAULT_PLAYER_ENGINE
                )
            else:
                engine_string = settings.get_config_key(
                    'DEFAULT_ENGINE', settings.DEFAULT_ENGINE
                )

        with models.Session(models.engine) as session:
            character = models.Character.get(name, category_str, session)

            change = False
            if self.rank == "primary" and character.engine != engine_string:
                character.engine = engine_string
                change = True
            elif self.rank == "secondary" and character.engine_secondary != engine_string:
                character.engine_secondary = engine_string
                change = True

            if change:
                log.debug(
                    f'''Saving {self.rank} changed engine_string {character.name}
                        {character.engine=} 
                        {character.engine_secondary=} 
                        {self.rank=}
                        {engine_string=}
                    ''', 
                )

                session.commit()

    def load_character_engines(self, session):
        """
        We've set the character name, we want the rest of the metadata to
        populate.  Setting the engine name should domino the rest.
        """
        try:
            character = models.get_selected_character()
        except models.NoCharacterSelected:
            return
       
        if character.engine in ["", None]:
            if character.category == "player":
                self.selected_engine.set(settings.get_config_key(
                    'DEFAULT_PLAYER_ENGINE', settings.DEFAULT_ENGINE
                ))
            else:
                self.selected_engine.set(settings.get_config_key(
                    'DEFAULT_ENGINE', settings.DEFAULT_ENGINE
                ))
        else:
            log.debug(f'Setting {self.rank} engine to either ({character.engine} | {character.engine_secondary})')
            if self.rank == "primary":
                self.selected_engine.set(character.engine)
            elif self.rank == "secondary":
                self.selected_engine.set(character.engine_secondary)
            
        return character


class EffectList(ctk.CTkFrame):
    def __init__(self, master, *args, **kwargs):       
        super().__init__(master, *args, **kwargs)

        self.name = None
        self.category = None
        self.next_effect_row = 0
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.add_effect_combo = AddEffect(self, self)
        self.add_effect_combo.grid(
            column=0, row=0, sticky="new"
        )

    def load_effects(self, name, category):
        log.debug('EffectList.load_effects()')

        self.name = name
        self.category = category

        # teardown any effects already in place
        #for effect in models.get_effects():

        models.wipe_all_effects()

        with models.db() as session:
            character = models.Character.get(name, category, session)
            
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

            index = -1
            for index, effect in enumerate(voice_effects):
                log.debug(f'Adding effect {effect} found in the database')
                effect_class = registry.get_effect(effect.effect_name)

                ttk.Style().configure(
                    "Effect.TFrame",
                    highlightbackground="black", 
                )

                # not very DRY
                effect_config_frame = effect_class(self)
                effect_config_frame.grid(row=index, column=0, sticky="new")
                #pack(side="top", fill="x", expand=True)
                effect_config_frame.effect_id.set(effect.id)
                models.add_effect(effect_config_frame)

                effect_config_frame.load()
            
            self.next_effect_row = index + 1

            log.debug("Rebuilding add_effect")
            self.add_effect_combo.grid_forget()
            self.add_effect_combo = AddEffect(self, self)
            self.add_effect_combo.grid(
                row=self.next_effect_row, 
                column=0, 
                sticky="new"
            )


    def add_effect(self, effect_name):
        """
        Add the chosen effect to the list of effects the user can manipulate.

        effect name is the nice, button friendly string.  Using it as the
        index for effects.EFFECTS is a bit dirty.  The button should have a
        companion value other than the label, the we can just use that as an
        index.

        This call is for new effects which will start with default configurations.
        """
        effect = registry.get_effect(effect_name)
        
        # effect is one of the EffectParameterEditor objects in effects.py
        if effect:
            #
            # effect_config_frame is an instance of one of the
            # EffectParameterEditor objects in effects.py.  They inherit
            # from ttk.Frame. 
            #
            # Instantiating these objects creates any tk objects they need to
            # configure themselves and the ttk.Frame returned can then be
            # pack/grid whatever to arrange the screen.
            # 
            # When we go to render we expect each effect to provide a
            # get_effect(self) that returns an Effect: 
            #   https://github.com/austin-bowen/voicebox/blob/main/src/voicebox/effects/effect.py#L9
            # with an apply(Audio) that returns an Audio; An "Audio" is a pretty
            # simple object wrapping a np.ndarray of [-1 to 1] samples.
            #
            effect_config_frame = effect(self)
            self.add_effect_combo.grid_forget()
            effect_config_frame.grid(
                column=0, 
                row=self.next_effect_row, 
                sticky="new"
            )

            self.next_effect_row += 1
            log.debug("Rebuilding add_effect")
            self.add_effect_combo.grid(
                row=self.next_effect_row, 
                column=0, 
                sticky="new"
            )

            models.add_effect(effect_config_frame)

            with models.Session(models.engine) as session:
                # retrieve this character
                character = models.Character.get(self.name, self.category, session)

                # save the current effect selection
                effect = models.Effects(
                    character_id=character.id,
                    effect_name=effect_name
                )
                session.add(effect)
                session.commit()
                session.refresh(effect)

            for key in effect_config_frame.tkvars:
                # save the current effect configuration, these will presumably
                # just be the defaults.
                value = effect_config_frame.tkvars[key].get()

                new_setting = models.EffectSetting(
                    effect_id=effect.id,
                    key=key,
                    value=value
                )
                session.add(new_setting)
            session.commit()
            
            effect_config_frame.effect_id.set(effect.id)
            effect_config_frame.load()
    
    def remove_effect(self, effect_obj):
        log.debug(f'Removing effect {effect_obj}')
        
        # remove it from the effects list
        models.remove_effect(effect_obj)
        effect_id = effect_obj.effect_id.get()
        # remove it from the database
        with models.Session(models.engine) as session:
            # clear any effect settings
            session.execute(
                delete(models.EffectSetting).where(
                    models.EffectSetting.effect_id == effect_id
                )
            )

            # clear the effect itself
            session.execute(
                delete(models.Effects).where(
                    models.Effects.id == effect_id
                )
            )
            session.commit()

        # forget the widgets for this object
        effect_obj.grid_forget()
        # self.grid()


class AddEffect(ttk.Frame):
    # where is this 70 coming from?  you got it from where?  what the
    # hell buddy.  This is the shit that causing errors when people
    # use an app at different resolutions.  This will center at one spot
    # and all the other entries will be different.
    ADD_AN_EFFECT = "⪡  Add an Effect  ⪢"

    def __init__(self, master, effect_list, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.effect_list = effect_list

        # we're using the textvariable as the action associated with changing
        # this combobox.  That only gives us the scope of what can see this
        # selected_effect to either read the current value or trace_add to 
        # trigger whenever selected_effect is written to.       
        self.selected_effect = tk.StringVar(value=self.ADD_AN_EFFECT)
        self.selected_effect.trace_add("write", self.add_effect)

        effect_combobox = ttk.Combobox(
            self,
            textvariable=self.selected_effect
        )
        #effect_combobox.option_add('*TCombobox*Listbox.Justify', 'center')
        effect_combobox["values"] = registry.effect_list()
        effect_combobox["state"] = "readonly"

        #  <-[XXX    ]
        effect_combobox.pack(side="top", fill="x", expand=True)

        #  [XXX]->
        # ttk.Button(self, text="Add Effect", command=self.add_effect).pack(side="right")

    def add_effect(self, varname, lindex, operation):
        # Retrieve the currently selected effect from the
        # tk.StringVar.
        effect_name = self.selected_effect.get()
        # effect_list provides a very handy helper to make this easy.  Our
        # output is just providing this effect_list[] for anyone that wants it.
        # Sounds kind of stupid when you actually type it out.
        self.effect_list.add_effect(effect_name)
               
        # reset the UI back to the "add an effect" prompt
        self.selected_effect.set(self.ADD_AN_EFFECT)


class BiographyFrame(ctk.CTkFrame):
    def __init__(
            self, 
            master, 
            character_name, 
            group_name, 
            character_description, 
            *args, 
            **kwargs
        ):
        super().__init__(master, *args, **kwargs)

        self.columnconfigure(0, weight=1)
        self.rowconfigure((0, 1), weight=0)
        self.rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self,
            textvariable=character_name,
            anchor="center",
            font=ctk.CTkFont(
                size=22,
                weight="bold"
            )
        ).grid(column=0, row=0, sticky="ew")

        # which group is this npc a member of.  this will
        # frequently not have a value
        ctk.CTkLabel(
            self,
            textvariable=group_name,
            wraplength=220,
            anchor="n",
            justify="center"
        ).grid(column=0, row=1, sticky="ew")

        # description of the character (if there is one)
        ctk.CTkLabel(
            self,
            textvariable=character_description,
            wraplength=350,
            anchor="nw",
            justify="left"
        ).grid(column=0, row=2, sticky="nsew")


class DetailSide(ctk.CTkScrollableFrame):
    """
    Primary frame for the "detail" side of the application.
    """
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)

        self.listside = None
        self.trashcan = Feather(
            'trash-2',
            size=22
        )

        # biography
        self.rowconfigure(0, weight=0)
        
        # enginenotebook
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self.character_name = tk.StringVar()
        self.group_name = tk.StringVar()
        self.character_description = tk.StringVar()

        biography = BiographyFrame(
            self, 
            character_name=self.character_name,
            group_name=self.group_name,
            character_description=self.character_description
        )

        ctk.CTkButton(
            biography,
            image=self.trashcan.CTkImage,
            text="",
            width=40,
            command=self.remove_character
        ).place(relx=1, rely=0, anchor='ne')

        biography.grid(column=0, row=0, sticky='nsew')

        self.engine_notebook = ctk.CTkTabview(
            self,
            anchor="nw"
        )
        self.engine_notebook.grid_rowconfigure(0, weight=1)
        self.engine_notebook.grid_rowconfigure(1, weight=1)
        self.engine_notebook.grid_columnconfigure(0, weight=1)

        primary = self.engine_notebook.add('Primary')
        primary.grid_rowconfigure(0, weight=1)
        primary.grid_columnconfigure(0, weight=1)

        secondary = self.engine_notebook.add('Secondary')
        secondary.grid_rowconfigure(0, weight=1)
        secondary.grid_columnconfigure(0, weight=1)
        
        effects = self.engine_notebook.add('Effects')
        effects.grid_rowconfigure(0, weight=1)
        effects.grid_columnconfigure(0, weight=1)

        randomize = ctk.CTkButton(
            self.engine_notebook, 
            text="Randomize", 
            command=self.shuffle,
            width=100
        )
        randomize.place(relx=1, rely=0.014, anchor='ne')

        self.primary_tab = EngineSelectAndConfigure(
            'primary', primary, 
        )
        self.primary_tab.grid(column=0, row=0, sticky="nsew")

        self.secondary_tab = EngineSelectAndConfigure(
            'secondary', secondary, 
        )
        self.secondary_tab.grid(column=0, row=0, sticky="nsew")

        # list of effects already configured
        self.effect_list = EffectList(effects)
        self.effect_list.grid(column=0, row=0, sticky="nsew")

        self.engine_notebook.grid(column=0, row=1, sticky="nsew")
        #.pack(side="top", fill="x", expand=True)

        #self.bind('<Enter>', self._bound_to_mousewheel)
        #self.bind('<Leave>', self._unbound_to_mousewheel)

    def shuffle(self, *args, **kwargs):
        """
        Choose new random values for the currenty selected engine config
        """
        panel = self.engine_notebook.get()
        log.info(f"{panel=}")
        character = models.get_selected_character()
        with models.db() as session:
            models.Character.create_character(
                name=character.name,
                category=character.category,
                session=session,
                character=character
            )
        
        self.load_character(character.category, character.name)
        return

    def selected_category_and_name(self):
        """
        returns tuple of category, name, item
        """
        return self.listside.selected_category_and_name()

    # def _bound_to_mousewheel(self, event):
    #     self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    # def _unbound_to_mousewheel(self, event):
    #     self.canvas.unbind_all("<MouseWheel>")

    # def _on_mousewheel(self, event):
    #     top, bottom = self.vsb.get()
    #     if top > 0.0 or bottom < 1.0:
    #         self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def remove_character(self):
        if self.listside:
            self.listside.delete_selected_character()

    # def onFrameConfigure(self, event):
    #     """Reset the scroll region to encompass the inner frame"""
    #     # Update the scrollbars to match the size of the inner frame.
    #     size = (self.frame.winfo_reqwidth(), self.frame.winfo_reqheight())
    #     self.canvas.config(scrollregion="0 0 %s %s" % size)
    #     if self.frame.winfo_reqwidth() != self.canvas.winfo_width():
    #         # Update the canvas's width to fit the inner frame.
    #         self.canvas.config(width=self.frame.winfo_reqwidth())        

    #     # self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # def onCanvasConfigure(self, event):
    #     if self.frame.winfo_reqwidth() != self.canvas.winfo_width():
    #         # Update the frame width to fill the canvas.
    #         self.canvas.itemconfigure(
    #             self.frame_id, 
    #             width=self.canvas.winfo_width()
    #         )

    def load_character(self, category, name):
        """
        load this NPC and populate the detailside widgets
        """
        # set the engine
        # set engine parameters
        # loop effects
        # add each effect
        # set parameters for each effect
        log.debug(f'DetailSide.load_character({name})')
           
        # TODO: "choose" and highlight this character on the listside
        group_name = ""

        models.set_selected_character(
            name, category
        )

        self.character_name.set(name)

        if category == "npc":
            npc_data = settings.get_npc_data(name)
            description = ""   
            if npc_data:
                description = npc_data["description"]
                group_name = npc_data["group_name"]
            self.character_description.set(description)
            self.group_name.set(group_name)
        elif category == "":
            return
        else:
            self.character_description.set("")
            self.group_name.set("Unaffiliated")

        # load the character 
        with models.db() as session:
            character = models.Character.get(name, category, session)
        
            if not character.group_name and group_name:
                character.group_name = group_name
                session.commit()

        # set the engines itself
        # log.debug('b character: %s | %s | %s', character, character.engine, character.engine_secondary)
        self.primary_tab.set_engine(character.engine)
        self.secondary_tab.set_engine(character.engine_secondary)

        # set engine and parameters
        if self.primary_tab.engine_parameters:
            self.primary_tab.engine_parameters.load_character(category, name)
        
        if self.secondary_tab.engine_parameters:
            self.secondary_tab.engine_parameters.load_character(category, name)
        
        # effects
        self.effect_list.load_effects(
            name=name,
            category=category
        )

        # reset the preset selector
        # self.presetSelect.reset()

        # scroll to the top
        # self.vsb.set(0, 1)
        # self.canvas.yview_moveto(0)


class ListSide(ctk.CTkFrame):
    def __init__(self, master, detailside, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.detailside = detailside
        #wait, what?
        self.detailside.listside = self

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)

        self.list_filter = tk.StringVar(value="")
        listfilter = ctk.CTkEntry(
            self,
            width=40,
            textvariable=self.list_filter
        )
        listfilter.grid(
            column=0, 
            row=0, 
            columnspan=2, 
            sticky="ew"
        )

        self.list_filter.trace_add('write', self.apply_list_filter)

        #listarea = ctk.CTkFrame(self)
        columns = ('name', )
        self.character_tree = ttk.Treeview(
            self,  # listarea, 
            selectmode="browse", 
            columns=columns, 
            show=''
        )
        self.character_tree.column('name', width=200, stretch=tk.YES)       
        self.refresh_character_list()
        self.character_tree.grid(column=0, row=1, sticky='nsew')

        vsb = ctk.CTkScrollbar(
            self,
            command=self.character_tree.yview
        )
        self.character_tree.configure(yscrollcommand=vsb.set)

        self.bind('<Enter>', self._bound_to_mousewheel)
        self.bind('<Leave>', self._unbound_to_mousewheel)

        vsb.grid(column=2, row=1, sticky='ns')

        ctk.CTkButton(
            self,
            text="Refresh",
            command=self.refresh_character_list
        ).grid(column=0, columnspan=3, row=2, sticky='e')

        self.character_tree.bind("<<TreeviewSelect>>", self.character_selected)

    def _bound_to_mousewheel(self, event):
        self.character_tree.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbound_to_mousewheel(self, event):
        self.character_tree.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self.character_tree.yview_scroll(int(-1*(event.delta/120)), "units")

    def apply_list_filter(self, a, b, c):
        self.refresh_character_list()

    def selected_category_and_name(self):
        """
        returns currently selected category, name, item
        """
        item = self.get_selected_character_item()
        if item is None:
            return None, None, None
        
        name = item["values"][0]

        category = None
        if 'player' in item['tags']:
            category = "player"
        elif 'npc' in item['tags']:
            category = 'npc'
        elif 'system' in item['tags']:
            category = 'system' 

        return category, name, item

    def character_selected(self, event=None):
        category, name, item = self.selected_category_and_name()

        if name is None:
            return

        if category:
            self.detailside.load_character(category, name)
        else:
            # click group row to open/close that group
            if item['open']:
                self.character_tree.item(
                    self.character_tree.selection()[0], 
                    open=False
                )
            else:
                self.character_tree.item(
                    self.character_tree.selection()[0], 
                    open=True
                )

    def refresh_character_list(self):
        log.debug('Refreshing Character list from the database...')

        filter_string = self.list_filter.get()

        with models.db() as session:
            all_characters = session.scalars(
                select(
                    models.Character
                ).order_by(
                    desc(models.Character.last_spoke),
                ).order_by(
                    models.Character.category,
                )
            ).all()

            # yes, this could/should be baked into the query and that would be 
            # more efficient
            if filter_string not in [None, ""]:
                all_characters = [
                    character for character in all_characters if filter_string.upper() in character.name.upper()
                ]

        if all_characters:
            self.character_tree.delete(*self.character_tree.get_children())
            self.character_tree["columns"] = ("Name", )
            
            groups = {}
            first = None
            player_category = models.category_str2int("player")
            for c in all_characters:
                if c.group_name:
                    parent = groups.get(c.group_name)
                    if parent is None:
                        log.debug(f'Creating new group for {c.group_name!r}')
                        parent = self.character_tree.insert(
                            "", 
                            'end', 
                            values=(c.group_name, ),
                            tags=('grouprow')
                        )
                        groups[c.group_name] = parent
                    tag = "member"
                elif c.category == player_category:
                    parent = groups.get("Players")
                    if parent is None:
                        log.debug('Creating new group for Players')
                        parent = self.character_tree.insert(
                            "", 
                            'end', 
                            values=("Players", ),
                            tags=('grouprow')
                        )
                        groups["Players"] = parent
                    tag = "member"
                else:
                    # log.debug(f'Not a player or group member {c=}')
                    parent = ""
                    tag = "base"

                node = self.character_tree.insert(
                    parent, 
                    'end', 
                    values=(c.name, ),
                    tags=(models.category_int2str(c.category), tag)
                )

                if first is None:
                    first = node

            # resetting to the first entry is obviously wrong
            self.character_tree.selection_set(
                [first, ]
            )
            
            self.character_tree.tag_configure('grouprow', background='grey28', foreground='white')
            self.character_tree.tag_configure('member', background='grey60', foreground='black')
    
    def delete_selected_character(self):
        category, name, item = self.selected_category_and_name()

        log.debug(f'Deleting character {name!r}')
        log.debug(f'Name: {name!r}  Category: {category!r}')
        
        with models.db() as session:
            character = models.Character.get(name, category, session)

            session.execute(
                delete(
                    models.BaseTTSConfig
                ).where(
                    models.BaseTTSConfig.character_id == character.id
                )
            )

            session.execute(
                delete(
                    models.Phrases
                ).where(
                    models.Phrases.character_id == character.id
                )
            )

            all_effects = session.scalars(
                select(
                    models.Effects
                ).where(
                    models.Effects.character_id == character.id
                )
            ).all()
            for effect in all_effects:
                session.execute(
                    delete(
                        models.EffectSetting
                    ).where(
                        models.EffectSetting.effect_id == effect.id
                    )
                )

            session.execute(
                delete(
                    models.Effects
                ).where(
                    models.Effects.character_id == character.id
                )
            )

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

        # TODO: dude, delete everything they have ever said from
        # disk too.
        # self.refresh_character_list()

        current_item = self.character_tree.selection()[0]
        # if we have a sibling, move the selection to the next sibling
        sibling = self.character_tree.next(current_item)
        self_delete = True
        if sibling:
            self.character_tree.selection_set(sibling)
        else:
            # we do not have a next siblings. Maybe a previous sibling?
            sibling = self.character_tree.prev(current_item)
            if sibling:
                self.character_tree.selection_set(sibling)
            else:
                # no next, no previous.  parent.
                parent = self.character_tree.parent(current_item)
                if parent:
                    # so we have a parent with no children.
                    # get rid of it.
                    sibling = self.character_tree.prev(parent)
                    self.character_tree.delete(parent)                    
                    self.character_tree.selection_set(sibling)
                    self_delete = False
        
        if self_delete:
            # if our parent was deleted because we were the last
            # member of the group this will fail with an error.
            self.character_tree.delete(current_item)
        # self.character_tree.selection_remove(current_item)

        # de-select the previously chosen item (which should be gone anyway)
        #for item in self.character_tree.selection():
        #    
        
        # why do this by hand?
        # self.character_tree.event_generate("<<TreeviewSelect>>")

    def get_selected_character_item(self):
        if len(self.character_tree.selection()) == 0:
            # we de-selected everything
            # TODO: wipe the detail side?
            return

        item = self.character_tree.item(
            self.character_tree.selection()[0]
        )
       
        return item
