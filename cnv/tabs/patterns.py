
import logging
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
import cnv.lib.settings as settings
import os
import json
from cnv.engines.base import registry as engine_registry
from cnv.chatlog import patterns

log = logging.getLogger(__name__)

# so this can be a whole good thing.  We need to figure out how the translate
# apis work on our various engines the we can make this work and not be so
# ridiculously terrible.


class PatternsTab(tk.Frame):
  
    def __init__(self, parent, event_queue, speaking_queue, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.detailside=None
        self.listside=None
       
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        detailside = PatternDetail(self)
        listside = PatternList(self, detailside)
        detailside.patternlist = listside

        listside.grid(column=0, row=0, sticky="nsew")
        detailside.grid(column=1, row=0, sticky="nsew")

        # auto-open the first item
        listside.pattern_tree.item(
            listside.pattern_tree.get_children()[0], 
            open=True
        )


class PatternDetail(ctk.CTkScrollableFrame):
    """
    """
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.patternlist = None

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=2)

        self.regex_txvar = tk.StringVar()
        ctk.CTkLabel(
            self,
            text="Regular Expression",
            anchor="e"
        ).grid(row=0, column=1, sticky="e")

        self.regex = ctk.CTkEntry(self, textvariable=self.regex_txvar, width=300)
        self.regex.grid(row=0, column=2, sticky="ew")

        ctk.CTkLabel(
            self,
            text="Example Text",
            anchor="e"
        ).grid(row=1, column=1, sticky="e")
        self.example = ctk.CTkTextbox(
            self, 
            wrap=tk.WORD,
            height=100
        )
        self.example.grid(row=1, column=2, sticky="nsew")

        self.toggles_txvar = tk.StringVar()
        # CTkComboBox() widget with each of the known toggles as options
        ctk.CTkLabel(
            self,
            text="Toggle Category",
            anchor="e"
        ).grid(row=2, column=1, sticky="e")
        
        self.toggles = ctk.CTkComboBox(
            master=self,
            values=patterns.get_known_toggles(),
            #variable=self.toggles_txvar,
            width=200,
        )
        self.toggles.grid(row=2, column=2, sticky="nsew")

        # self.channels_txvar = tk.StringVar()
        # CTkComboBox() widget with each of the known toggles as options
        # ctk.CTkLabel(
        #     self,
        #     text="Channel",
        #     anchor="e"
        # ).grid(row=2, column=1, sticky="e")

        # this is dumb, these _all_ have to be "system"
        # self.channels = ctk.CTkComboBox(
        #     master=self,
        #     values=['npc', 'system', 'player'],
        #     variable=self.channels_txvar,
        #     width=200,
        # )
        # self.channels.grid(row=2, column=2, sticky="nsew")
        self.enabled_txvar = tk.BooleanVar(value=True)
        self.enabled = ctk.CTkCheckBox(
            master=self,
            text="Enabled",
            variable=self.enabled_txvar
        )
        self.enabled.grid(row=3, column=2, sticky="nsew")

        self.strip_number_txvar = tk.BooleanVar(value=False)
        self.strip_number = ctk.CTkCheckBox(
            master=self,
            text="Strip Numbers",
            variable=self.strip_number_txvar
        )
        self.strip_number.grid(row=4, column=2, sticky="nsew")

        self.soak_txvar = tk.IntVar(value=0)
        self.soak = ctk.CTkEntry(
            master=self,
            textvariable=self.soak_txvar,
            width=50
        )
        self.soak.grid(row=5, column=2, sticky="nsew")
        ctk.CTkLabel(
            self,
            text="Soak Time (sec)",
            anchor="e"
        ).grid(row=5, column=1, sticky="e")

        self.save_button = ctk.CTkButton(
            master=self,
            text="Save Pattern",
            command=self.save_pattern
        ).grid(
            row=6, column=2, sticky="nsew"
        )

    def save_pattern(self, event=None):
        """
        Save the current pattern details to the pattern list.
        """
        if self.patternlist is None:
            log.error("Pattern list is not set.")
            return

        selected = self.patternlist.pattern_tree.selection()

        if not selected:
            log.error("No pattern selected to save.")
            return
        
        item_options = self.patternlist.pattern_tree.item(
            selected[0]
        )
    
        parent = self.patternlist.pattern_tree.parent(selected[0])

        # if we are here, this should be a member item
        assert 'member' in item_options['tags']  # sanity check

        pattern_name = item_options['values'][0]
        prefix_name = item_options['values'][1]

        hindex = self.patternlist.pattern_tree.index(
            selected[0]
        )
        log.info('pattern %s in prefix %s lives at index %d', pattern_name, prefix_name, hindex)

        if not pattern_name:
            log.error("Pattern name cannot be empty.")
            return

        pattern = {
            'regex': self.regex_txvar.get(),
            'example': self.example.get(1.0, tk.END).strip(),
            'toggle': self.toggles.get(),
            'channel': 'system',  # hardcoded for now
            'enabled': self.enabled_txvar.get(),
            'strip_number': self.strip_number_txvar.get(),
            'soak': float(self.soak_txvar.get())
        }

        log.info('Saving pattern: %s', pattern)
        # Save the pattern to the list

        patterns.delete_pattern(prefix_name, pattern_name)
        patterns.save_pattern(prefix_name, self.regex_txvar.get(), pattern, hindex)

        # we should update the currently highlighted listing in self.patternlist if regex has changed.
        #3 self.patternlist.hot_set_selected_pattern(pattern_name)
        self.patternlist.refresh_pattern_list(
            prefix=prefix_name,
            hindex=hindex,
        )

        # resetting to the first entry is obviously wrong
        # find our new node, and make it the selected item.
        #node = self.patternlist.pattern_tree.item()
        # open the prefix
        #parent = self.patternlist.pattern_tree.parent(node)
        #if parent:



    def load_pattern(self, prefix_name, pattern_name):
        # Load the pattern details into the detail side
        pattern = patterns.get_pattern(prefix_name, pattern_name)

        NOT_SET = '<< Not Set >>'

        if pattern:
            toggle_values = [ NOT_SET, ] + patterns.get_known_toggles()
            self.toggles['values'] = toggle_values
            
            log.debug(f"Loading pattern: {pattern}")
            
            self.regex_txvar.set(pattern['regex'])

            self.example.delete(1.0, tk.END)
            self.example.insert(tk.END, pattern.get('example', ''))

            self.toggles.set(pattern.get('toggle', NOT_SET))

            self.enabled_txvar.set(pattern.get('enabled', True))
            self.strip_number_txvar.set(pattern.get('strip_number', False))
            self.soak_txvar.set(pattern.get('soak', 0.0))


class PatternList(ctk.CTkFrame):
    def __init__(self, master, detailside, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.detailside = detailside
        #wait, what?
        self.detailside.patternlist = self

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

        columns = ('pattern', )
        self.pattern_tree = ttk.Treeview(
            master=self,  
            selectmode="browse", 
            columns=columns,
            show=''
        )
        self.pattern_tree.column('pattern', width=200, stretch=tk.YES)
        self.refresh_pattern_list()
        self.pattern_tree.grid(column=0, row=1, sticky='nsew')

        vsb = ctk.CTkScrollbar(
            self,
            command=self.pattern_tree.yview
        )
        self.pattern_tree.configure(yscrollcommand=vsb.set)

        self.bind('<Enter>', self._bound_to_mousewheel)
        self.bind('<Leave>', self._unbound_to_mousewheel)

        vsb.grid(column=2, row=1, sticky='ns')
        self.pattern_tree.bind("<<TreeviewSelect>>", self.pattern_selected)

    def _bound_to_mousewheel(self, event):
        self.pattern_tree.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbound_to_mousewheel(self, event):
        self.pattern_tree.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self.pattern_tree.yview_scroll(int(-1*(event.delta/120)), "units")

    def apply_list_filter(self, a, b, c):
        self.refresh_pattern_list()

    # def hot_set_selected_pattern(self, pattern_name):
    #     """
    #     Set the currently selected pattern to the one with the given name.
    #     """
    #     # what is the currently selected item?
        
    #     selected = self.pattern_tree.selection()
    #     log.info('the selected item is %s', selected)
    #     #
    #     # selected_item is one item in a Treeview
    #     # https://docs.python.org/3/library/tkinter.ttk.html#tkinter.ttk.Treeview

    #     values = self.pattern_tree.item(selected[0])
    #     log.info('values are: %s', values)

    #     # they make this difficult.
    #     selected_index = self.pattern_tree.index(selected[0])
    #     parent = self.pattern_tree.parent(selected[0])

    #     self.pattern_tree.delete(selected[0])
        
    #     new_item_str = self.pattern_tree.insert(
    #         parent=parent,
    #         index=selected_index,
    #         text=pattern_name,
    #         values=(pattern_name, values["values"][1]),
    #         tags=("member", )
    #     )

    #     self.pattern_tree.selection_set([new_item_str, ])

    #     #self.pattern_tree.set(selected, "pattern", pattern_name)
    #     #self.pattern_tree.set(selected, "values", (pattern_name, values["values"][1]))
    #     # self.pattern_tree.item(
    #     #     item=selected[0], 
    #     #     option=None, 
    #     #     # **kwargs=
    #     #     text=pattern_name, 
    #     #     values=(pattern_name, values[1])
    #     # )

    def pattern_selected(self, event=None):
        """
        One of the items in the list was clicked on
        """
        item_str = self.pattern_tree.selection()[0]
        # selection returns a list of strings, that are somehow really items.

        log.debug('item is %s', item_str)

        if not item_str:
            log.warning('No item selected.')
            return

        # turn it into a _real_ item
        item = self.pattern_tree.item(
            item_str
        )

        # what kind of thing did they click on?
        # Ah, it's a prefix pattern
        if 'grouprow' in item['tags']:
            # when a user clicks the group name, it opens/closes that group
            if item['open']:
                self.pattern_tree.item(
                    self.pattern_tree.selection()[0],
                    open=False
                )
            else:
                self.pattern_tree.item(
                    self.pattern_tree.selection()[0],
                    open=True
                )        
        elif 'member' in item['tags']:
            # we want to populate the detailside with the chosen
            # pattern.
            log.info('Loading pattern %s', item['values'])
            self.detailside.load_pattern(
                pattern_name=item['values'][0],
                prefix_name=item['values'][1]
            )

        return item

    def refresh_pattern_list(self, prefix=None, hindex=0):
        log.debug('Refreshing pattern list...')

        all_patterns = patterns.load_patterns()

        # wipe the pattern tree
        if self.pattern_tree:
            self.pattern_tree.delete(*self.pattern_tree.get_children())
            #self.pattern_tree["columns"] = ("Name", )
        selected = None
        selected_parent = None
        for pattern_prefix in all_patterns:
            parent = self.pattern_tree.insert(
                parent="",  # top level item
                index='end',
                text=pattern_prefix['prefix'],
                values=(pattern_prefix['prefix'], ),
                tags=('grouprow', )
            )

            for index, p in enumerate(pattern_prefix["patterns"]):
                log.debug('Adding pattern %s', p['regex'])

                node = self.pattern_tree.insert(
                    parent=parent,
                    index='end',
                    text=p['regex'],
                    values=(p['regex'], pattern_prefix['prefix']),
                    tags=("member", )
                )

                if pattern_prefix['prefix'] == prefix and index == hindex:
                    log.info(f'Setting {parent=} and {node=}')
                    selected_parent = parent
                    selected = node
                else:
                    log.debug(f"{pattern_prefix['prefix']} != {prefix}")
                    log.debug(f"{index=} != {hindex=}")

        if selected_parent:
            self.pattern_tree.item(
                selected_parent,
                open=True
            )

                # if pattern_prefix == prefix and index == hindex:
                #     for child in self.pattern_tree.get_children():
                #         if self.pattern_tree.item(child, 'values')[1] == pattern_prefix['prefix']:
                #             selected = child

                #             log.info('Expanding prefix %s', pattern_prefix['prefix'])

                #             break
                #         else:
                #             log.info('Skipping child %s (%s != %s)', child, self.pattern_tree.item(child, 'values')[1], pattern_prefix['prefix'])

        # If we found the matching index, select this node
        if selected:
            self.pattern_tree.selection_set(
                [selected, ]
            )                        


        self.pattern_tree.tag_configure('grouprow', background='grey28', foreground='white')
        self.pattern_tree.tag_configure('member', background='grey60', foreground='black')
  

    # def delete_selected_character(self):
    #     category, name, item = self.selected_category_and_name()

    #     log.debug(f'Deleting character {name!r}')
    #     log.debug(f'Name: {name!r}  Category: {category!r}')
        
    #     with models.db() as session:
    #         character = models.Character.get(name, category, session)

    #         session.execute(
    #             delete(
    #                 models.BaseTTSConfig
    #             ).where(
    #                 models.BaseTTSConfig.character_id == character.id
    #             )
    #         )

    #         session.execute(
    #             delete(
    #                 models.Phrases
    #             ).where(
    #                 models.Phrases.character_id == character.id
    #             )
    #         )

    #         all_effects = session.scalars(
    #             select(
    #                 models.Effects
    #             ).where(
    #                 models.Effects.character_id == character.id
    #             )
    #         ).all()
    #         for effect in all_effects:
    #             session.execute(
    #                 delete(
    #                     models.EffectSetting
    #                 ).where(
    #                     models.EffectSetting.effect_id == effect.id
    #                 )
    #             )

    #         session.execute(
    #             delete(
    #                 models.Effects
    #             ).where(
    #                 models.Effects.character_id == character.id
    #             )
    #         )

    #         try:
    #             session.execute(
    #                 delete(models.Character)
    #                 .where(
    #                     models.Character.name == name,
    #                     models.Character.category == models.category_str2int(category)
    #                 )
    #             )
    #             session.commit()

    #         except Exception as err:
    #             log.error(f'DB Error: {err}')
    #             raise

    #     # TODO: dude, delete everything they have ever said from
    #     # disk too.
    #     # self.refresh_character_list()

    #     current_item = self.character_tree.selection()[0]
    #     # if we have a sibling, move the selection to the next sibling
    #     sibling = self.character_tree.next(current_item)
    #     self_delete = True
    #     if sibling:
    #         self.character_tree.selection_set(sibling)
    #     else:
    #         # we do not have a next siblings. Maybe a previous sibling?
    #         sibling = self.character_tree.prev(current_item)
    #         if sibling:
    #             self.character_tree.selection_set(sibling)
    #         else:
    #             # no next, no previous.  parent.
    #             parent = self.character_tree.parent(current_item)
    #             if parent:
    #                 # so we have a parent with no children.
    #                 # get rid of it.
    #                 sibling = self.character_tree.prev(parent)
    #                 self.character_tree.delete(parent)                    
    #                 self.character_tree.selection_set(sibling)
    #                 self_delete = False
        
    #     if self_delete:
    #         # if our parent was deleted because we were the last
    #         # member of the group this will fail with an error.
    #         self.character_tree.delete(current_item)
    #     # self.character_tree.selection_remove(current_item)

    #     # de-select the previously chosen item (which should be gone anyway)
    #     #for item in self.character_tree.selection():
    #     #    
        
    #     # why do this by hand?
    #     # self.character_tree.event_generate("<<TreeviewSelect>>")

    # def get_selected_character_item(self):
    #     if len(self.character_tree.selection()) == 0:
    #         # we de-selected everything
    #         # TODO: wipe the detail side?
    #         return

    #     item = self.character_tree.item(
    #         self.character_tree.selection()[0]
    #     )
       
    #     return item
