
import logging
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
import cnv.lib.settings as settings
import sys
import requests
import hashlib
import os
import zipfile
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding, utils
import base64


log = logging.getLogger(__name__)


PUBLIC_KEY = b'''-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEApFAPwfc3WP1VdgQSOfRB
nAufQtT7aGqv63loVQ2D4l19LIR/F9xRSu63E1X2cMi573F/96jKqSHFcbV+m6QE
AczftEguQ/RzCUGLmxDPREfErEzGjxm4JhLOliVTD3cClHlC8Mzur5OO4VA7f0f2
7x3qubIFfVb0DF3yNcZE0mw2jNsgbhvO9f8/+I6pbg6KfQLNNa/EPG9PpO7rStmM
RTAi8Ogjci46qqg66Z4+ZQr91LuySG7LS6+Z1gasGhp5N10/p5JDhAYLU+dtPMBR
neI9oQVcDx2HvvRgBETb83OKLLVdsdZAfA9II2Xs3sNRS2TCjo/2cgj5NvJ9FZoD
ZwIDAQAB
-----END PUBLIC KEY-----
'''


class UpgradeTab(tk.Frame):
  
    def __init__(self, parent, event_queue, speaking_queue, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        # first display the current version number and the date it was released.
        current_version = settings.get_config_key('version', "Unknown")
        release_date = settings.get_config_key('release_date', "Unknown")

        ctk.CTkLabel(
            self,
            text=f"Current Version: {current_version}",
            anchor="w",
        ).pack(side="top", fill="x")

        ctk.CTkLabel(
            self,
            text=f"Release Date: {release_date}",
            anchor="w",
        ).pack(side="top", fill="x")

        ctk.CTkLabel(
            self,
            text="Check for updates?",
            anchor="w",
        ).pack(side="top", fill="x")

        ctk.CTkButton(
            self,
            text="Check Now",
            command=self.check_for_updates
        ).pack(side="top", fill="x")

    def perform_upgrade(self, current_version_metadata):
        # {
        #     "version": "v1.0.0",
        #     "release_date": "2024-01-01"
        #     "upgrade": {
        #         "file": "sidekick-1.0.0--2.0.0.patch.zip",
        #         "version": "v2.0.0",
        #         "signature": "base64 patch file signature",
        #         "release_date": "2024-01-02"
        #         "size": 123456
        #         "hash": "sha256 of the patch.zip"
        #     }
        # }
        log.info("Performing upgrade...")

        log.info(
            "Upgrading from %s to %s using file %s",
            current_version_metadata['version'],
            current_version_metadata['upgrade']['version'], 
            current_version_metadata['upgrade']['file']
        )
        # show a progress bar
        progress_bar = ctk.CTkProgressBar(self)
        progress_bar.pack(side="top", fill="x")
        progress_bar.start()

        CHUNK_SIZE = 8192

        patch_fn = current_version_metadata['upgrade']['file']

        # download the patch
        # https://github.com/jason-kane/coh_npc_voices/releases/download/v4.4.0.preview/sidekick-4.4.0.preview.zip
        patch_url = f"https://github.com/jason-kane/coh_npc_voices/releases/download/{current_version_metadata['upgrade']['version']}/{patch_fn}"
        response = requests.get(patch_url, stream=True)
        if response.status_code == 200:
            with open(patch_fn, 'wb') as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    f.write(chunk)
                    # update progress bar
                    progress_bar.set(progress_bar.get() + CHUNK_SIZE / current_version_metadata['upgrade']['size'])
        else:
            log.error("Failed to download patch: %s", response.status_code)
            return

        # generate a SHA of the patch
        hasher = hashes.Hash(hashes.SHA256())
        with open(patch_fn, 'rb') as f:
            while chunk := f.read(CHUNK_SIZE):
                hasher.update(chunk)
        hash = hasher.finalize()

        # decrypt the patch signature using the public key
        public_key = serialization.load_pem_public_key(PUBLIC_KEY)

        # decode the signature
        decoded_signature = base64.b64decode(
            current_version_metadata['upgrade']['signature']
        )

        # Verify the signature, this will raise an exception if the verification
        # fails.
        public_key.verify(
            decoded_signature,
            hash,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            utils.Prehashed(hashes.SHA256())
        )

        # if they match, iterate the files in the patch .zip file
        # we will also need a mechanism to determine which files
        # can be removed.
        #
        # this script is:
        #   sidekick/_internal/cnv/tabs/upgrade.py
        #
        # and we _never_ want to touch any file that isn't either:
        #   sidekick/sidekick.exe
        #   sidekick/_internal/*
        #
        # the "root" directory of the patch zip file is one directory above sidekick.
        #
        # same directory sidekick.exe is in, three directories above upgrade.py
        sidekick_base_directory = os.path.abspath(
            os.path.join(
                "..", "..", "..", "..",
                os.path.dirname(__file__)
            )
        )

        # make sure we are in the right place.
        assert os.path.exists(os.path.join(sidekick_base_directory, "sidekick"))
        assert os.path.exists(os.path.join(sidekick_base_directory, "sidekick", "sidekick.exe"))
        assert os.path.exists(os.path.join(sidekick_base_directory, "sidekick", "_internal"))

        # replace existing files within the sidekick directory with files from the patch zip file
        with zipfile.ZipFile(patch_fn, 'r') as zip:
            for fn in zip.namelist():
                if fn.startswith("sidekick/") or fn.startswith("sidekick/_internal/"):
                    destination_fn = os.path.join(sidekick_base_directory, fn)
                    if os.path.exists(destination_fn):
                        os.unlink(destination_fn)

                    log.info("Replacing %s", destination_fn)
                    zip.extract(fn, path=sidekick_base_directory)       

        # delete the patch
        os.unlink(patch_fn)

        # update our settings
        settings.set_config_key('version', current_version_metadata['upgrade']['version'])
        settings.set_config_key('release_date', current_version_metadata['upgrade']['release_date'])

        # restart sidekick
        os.execl(sys.executable, *sys.argv)


    def show_upgrade_prompt(self, current_version_metadata, new_version_metadata):
        log.info("Showing upgrade prompt...")
        # Here you would implement the logic to show a modal dialog
        # asking the user if they want to upgrade to the new version.
        # You can use the release_metadata to display relevant information.
        ctk.CTkMessageBox(
            title="Upgrade Available",
            message=f"Version upgrade {current_version_metadata['version']} -> {new_version_metadata['version']} is available.\n\n"
                    f"Release Date: {new_version_metadata['release_date']}\n"
                    "Would you like to upgrade?",
            icon="question",
            buttons=[
                ("Yes", lambda: self.perform_upgrade(current_version_metadata)),
                ("No", lambda: log.info("User chose not to upgrade."))
            ]
        ).show()

        return

    def check_for_updates(self):
        log.info("Checking for updates...")
        url = "https://raw.githubusercontent.com/jason-kane/coh_npc_voices/refs/heads/main/releases.json"
        # download the releases file
        response = requests.get(url)
        if response.status_code == 200:
            releases = response.json()
            # [{
            #     "version": "v1.0.0",
            #     "release_date": "2024-01-01"
            #     "upgrade": {
            #         "file": "sidekick-1.0.0--2.0.0.patch.zip",
            #         "version": "v2.0.0",
            #         "signature": "patch file signature",
            #         "release_date": "2024-01-02"
            #         "size": 123456
            #         "hash": "sha256 of the patch.zip"
            #     }
            # }]
            
            # find the _current_ version in the releases file
            current_version = settings.get_config_key('version', "Unknown")
            current_version_metadata = releases.get(current_version)
            new_version_metadata = releases.get(current_version_metadata.get('upgrade', [None])[-1])

            if new_version_metadata:
                log.info("Current version metadata found: %s", new_version_metadata)
                # popup a modal asking if the user wants to upgrade to version 2.0
                self.show_upgrade_prompt(current_version_metadata, new_version_metadata)

            else:
                log.warning("Current version metadata not found.")

        else:
            log.error("Failed to retrieve releases: %s", response.status_code)
            return
