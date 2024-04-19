GROUP_ALIASES = {
    "PsychicClockwork": "Clockwork",
    "ArachnosEndgame": "Arachnos",
    "TsooEndgame": "Tsoo",
    "CircleOfThorns": "Circle of Thorns",
    "DecayingEidolons": "Vahzilok"
}

PRESETS = {
    "Random Female": {
        "engine": "Windows TTS",
        "BaseTTSConfig": {
            "voice_name": ('random', 'female'),
            "rate": "1"
        }
    },
    "Random Male": {
        "engine": "Windows TTS",
        "BaseTTSConfig": {
            "voice_name": ('random', 'male'),
            "rate": "1"
        }
    },
    "Clockwork": {
        "engine": "Windows TTS",
        "BaseTTSConfig": {
            "voice_name": ('random', 'any'),
            "rate": "1"
        },
        "Effects": {
            "Vocoder": {
                "carrier_freq": "160",
                "min_freq": "80",
                "max_freq": "8000",
                "bands": "40",
                "bandwidth": "0.5",
                "bandpass_filter_order": "3"
            },
            "RingMod": {
                "carrier_freq": "160",
                "blend": "0.5",
                "carrier_wave": "sin"
            },
            "Normalize": {
                "max_amplitude": "1.0",
                "remove_dc_offset": True
            }
        }
    },
    "Vahzilok": {
        "engine": "Windows TTS",
        "BaseTTSConfig": {
            "voice_name": ('random', 'any'),
            "rate": "2"
        }, 
        "Effects": {
            "Chorus": {
                "rate_hz": "10.0",
                "mix": "0.5",
                "depth": "0.25",
                "feedback": "0.0"
            }
        }
    },
    "Circle of Thorns": {
        "engine": "Windows TTS",
        "BaseTTSConfig": {
            "voice_name": ('random', 'any'),
            "rate": "1.25"
        },
        "Effects": {
            "Delay": {
                "delay_seconds": "0.1",
                "feedback": "0.1",
                "mix": "0.1"
            }
        }
    }
}
