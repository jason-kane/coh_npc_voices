import logging
import customtkinter as ctk
import cnv.database.models as models
import cnv.voices.voice_editor as voice_editor

log = logging.getLogger(__name__)


class VoicesTab(ctk.CTkFrame):
    def __init__(self, parent, event_queue, speaking_queue, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.detailside=None
        self.listside=None
       
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        detailside = voice_editor.DetailSide(self)
        listside = voice_editor.ListSide(self, detailside)

        listside.grid(column=0, row=0, sticky="nsew")
        detailside.grid(column=1, row=0, sticky="nsew")

    def get_selected_character(self):
        if (self.detailside is None or self.listside is None):
            for child in self.winfo_children():
                if child.winfo_name() == "!detailside":
                    # log.info('Found detailside')
                    self.detailside = child
                elif child.winfo_name() == "!listside":
                    # log.info('Found listside')
                    self.listside = child
                else:
                    log.debug(f'{child.winfo_name()=}')
        
        #if self.listside:
            #log.info(dir(self.listside))
            #log.info(f"{self.listside=}")

        #if self.detailside:
        #    log.info(dir(self.detailside))
        #    log.info(f"{self.detailside=}")

        # returns a Character() object for the
        # currently selected npc or player.
        if self.listside:
            category, name, _ = self.listside.selected_category_and_name()
            with models.db() as session:
                character = models.Character.get(name, category, session)
            return character
        else:
            return None
