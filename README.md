# What is this?

This program was a fairly simplistic python program that watches the City of Heroes chat log file.  When it sees a message from an NPC, it uses the windows text-to-speech capability to read out the message.  It also notices when you receive a badge and tells you which badge you got.

It still does that, mostly.

When coh_voices.exe starts you get a GUI.  It shows every character you've seen and allows you to modify the voice profile for each of them.

You can then "Attach to Log" and it will find the newest logfile in your CoH log dir, open it up and watch for additions.  When a character on the list says something, it speaks for them using their voice profile.  New characters are automatically entered with default values.

Paid text-to-speech services are supported.  Right now that means google text-to-speech.  You'll need a valid application default login.  https://cloud.google.com/sdk/gcloud/reference/auth/application-default/login  I know it is a pain.  The quality and flexibility are much better but it takes a moment to generate.  Responses are cached to keep costs down to near zero.  

The voice used by default is the free Windows TTS API system default voice.  You can apply voice effects.  They are part of the voice profile.

Overall I think this companion program makes City of Heroes a little more immersive.

# Installation

    pip install git+https://github.com/jason-kane/coh_npc_voices.git

# Upgrade

    pip install --upgrade git+https://github.com/jason-kane/coh_npc_voices.git

# Uninstall

    pip uninstall coh_npc_voices

# Adding Voices (Highly Recommended)

Making new free voices available is an easy way to increase the variety and flavor of voices you hear in the city.

## Windows 10

Open Settings, choose Time & Language
Choose Speech on the left side
Choose "Add voices" under Manage voices

By itselt that will probably only give you one or two more voices, even if you install a dozen.  There is a powershell script 'enable_all_win10_voices.ps' that copies voices from the "only use for windows transcribe" part of the registry out to the "use for anything" part.

You probably have to logout/login before the extra voices are available.

# Running it

Then open a cmd terminal and run:

    coh_voices.exe

First start City of Heroes, login and pick a character.  Then enable chat logging.

Per https://homecoming.wiki/wiki/Logchat_(Slash_Command)#:~:text=Slash%20Command%201%20The%20log%20files%20are%20stored,in%20Menu--%3E%20Options--%3E%20Windows%20tab--%3E%20Chat-%3E%20Log%20Chat. you can use this slash command in the chat window:

    /logchat

You will have to do this once for each character you want to enable.

You'll need to figure out where your logs are stored.  It will vary based on the installer.

    <COH Install Directory>/accounts/<Account Name>/logs/
    <COH Install Directory>/homecoming/accounts/<Account Name>/Logs/

Use "Set Log Dir" in the upper right corner to configure it for your log location.  You should only need to do this once.

Ocne you are ready You will need to click "Attach to Log" in the upper left corner after you are in-game.  The "Attach" button changes to a "Detach".  You can attach/detach whenever you want.

# Local Development

    git clone https://github.com/jason-kane/coh_npc_voices.git
    cd coh_npc_voices

The python source is in src/coh_npc_voices.  I've only made minimal efforts to make it nice.  It is tied to tkinter more than I would like.  The blend of multiprocess and threads is confusing; and core functionality is replicated for no good reason.

But it works, and it is fun.  Hence v1.


# Problems?

Please leave an issue here in github.  I can't promise anything but I'm very likely to read it.

# License?

MIT.  I think that means you are allowed to do what you want, just don't blame me if it all goes wrong.  That said I would appreciate pull requests if you make improvements so we can share the benefits.


# Dependencies

In many ways this is a UI wrapper around a mashup of these three modules:

https://github.com/austin-bowen/voicebox/
https://github.com/DeepHorizons/tts
https://github.com/spotify/pedalboard

Big thanks and shoutout for the creators of these packages.

Raw entity data from https://cod.uberguy.net/html/index.html
