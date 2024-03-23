# What is this?

This program is a fairly simplistic python program that watches the City of Heroes chat log file.  When it sees a message from an NPC, it uses the windows text-to-speech capability to read out the message.  It also notices when you receive a badge and tells you which badge you got.

I think it makes the game a little more immersive.  I intend to add more, similar things as the mood strikes.  More voices,  gendered voices and vocalized cut-scenes are obvious next steps.

# Installation

## Right now:

    pip install git+https://github.com/jason-kane/coh_npc_voices.git

# Running it

First start City of Heroes, login and pick a character.  Then enable chat logging.

Per https://homecoming.wiki/wiki/Logchat_(Slash_Command)#:~:text=Slash%20Command%201%20The%20log%20files%20are%20stored,in%20Menu--%3E%20Options--%3E%20Windows%20tab--%3E%20Chat-%3E%20Log%20Chat. you can use this slash command in the chat window:

    /logchat

You will have to do this once for each character you want to enable.

You'll need to figure out where your logs are stored.

    <COH Install Directory>/accounts/<Account Name>/logs/

Then open a cmd terminal and run:

    coh_npc_voices.exe --logdir c:/cityofheroes/myusername/Logs

# Problems?

Please leave an issue here in github.  I can't promise anything but I'm very likely to read it.

# License?

MIT.  I think that means you are allowed to do what you want, just don't blame me if it all goes wrong.  That said I would appreciate pull requests if you make improvements so we can share the benefits.
