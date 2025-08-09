import logging
import json
import os
log = logging.getLogger(__name__)


DEFAULT_PATTERNS =  [
    {
        "prefix": "You", 
        "enabled": True,
        'patterns': [
            {
                "regex": "search.*",
                "example": "You search through the crate",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "stopped.*",
                "example": "You stopped the Superadine shipment and arrested Chernobog Petrovic, one of the Skulls' founders!",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "managed.*",
                "example": "You managed to get a few more Skulls off the streets and made the city that much safer.",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "found.*",
                "example": "You found a face mask that is covered in some kind of mold. It appears to be pulsing like it's breathing. You send a short video to Watkins for evidence.\nYou found an odd clue from within the Vault Reserve building:  It would seem some suspicious individuals were storing weapons here, the Vault Reserve employee overheard them mention something called 'Operation: Kidnap Sinclair'.  All you need to do is track down who this 'Sinclair' is.\n\nYou found the Stabilizing Field that Proton was looking for, however the power core is missing!",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "have cleared.*",
                "example": "You have cleared the Snakes from the Arachnos base, and learned something interesting.",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "have destroyed.*",
                "example": "You have destroyed one of Proton's String Relay Transmitters.",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "stole.*",
                "example": "You stole the money!",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "begin.*",
                "example": "You begin",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "finished.*",
                "example": "You finished searching through the records\n\nYou finished searching the crate...",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "open.*",
                "example": "You open the records and find it filled with wooden tubes studded with holes. As you pick one up it emits a verbal record of the individual it is about.",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "did not.*",
                "example": "You did not find any usable equipment in the crate.",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "didn't.*",
                "example": "You didn't find Percy's Record",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "rescued.*",
                "example": "You rescued",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "have defeated.*",
                "example": "You have defeated",
                "toggle": "Acknowledge each win",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "have Insight.*",
                "example": "You have Insight into your enemy's weaknesses and slightly increase your chance To Hit and your Perception.",
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": False
            }, {
                "regex": "have Uncanny.*",
                "example": "You have Uncanny",
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "have been put.*",
                "example": "You have been put",
                "toggle": "Speak Debuffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "have been immobilized!.*",
                "example": "You have been immobilized!",
                "toggle": "Speak Debuffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "have been exemplared.*",
                "example": "You have been exemplared",
                "toggle": "",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "have been interrupted..*",
                "example": "You have been interrupted.",
                "toggle": "Speak Debuffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "have been held.*",
                "example": "You have been held",
                "toggle": "Speak Debuffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "have been temporarily.*",
                "example": "You have been temporarily",
                "toggle": "Speak Debuffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "have been blinded.*",
                "example": "You have been blinded",
                "toggle": "Speak Debuffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "have been granted.*",
                "example": "You have been granted",
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "have unclaimed.*",  # respecs and tailer sessions
                "example": "You have unclaimed",
                "toggle": "",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "are held!.*",
                "example": "You are held!",
                "toggle": "Speak Debuffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "are healed.*",
                "example": "You are healed by your Dehydrate for 23.04 health points over time.",
                "strip_number": True,
                "soak": 10,
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "are filled.*",
                "example": "You are filled",
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "are now.*",
                "example": "You are now",
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "are Robust.*",
                "example": "You are Robust",
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "are Enraged.*",
                "example": "You are Enraged",
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "are hidden.*",
                "example": "You are hidden",
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "are Sturdy.*",
                "example": "You are Sturdy",
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "carefully.*",
                "example": "You carefully",
                "toggle": "",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "look.*",
                "example": "You look",
                "toggle": "",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "find.*",
                "example": "You find",
                "toggle": "",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "activated.*",
                "example": "You activated",
                "toggle": "",
                "channel": "system",
                "enabled": False
            }, {
                "regex": "Taunt.*",
                "example": "You Taunt",
                "toggle": "",
                "channel": "system",
                "enabled": False
            }, {
                "regex": "received [0-9]+ reward merits.*",
                "example": "You received 6 reward merits.",
                "toggle": "Speak Merits",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "received .* \(Recipe\).*",
                "example": "You received Cacophony: Confuse/Range (Recipe).",
                "toggle": "Speak Merits",
                "channel": "system",
                "enabled": True
            }
        ]
    }, {
        "prefix": "Entering",
        "enabled": True,
        'patterns': [
            {
                "regex": ".* Medical Center.*",
                "toggle": "Snark",
                "append": [  # randomly selected
                    "Lets not do that again.",
                    "Try to be more careful.",
                    "Do you have a death wish?",
                    "You did that on purpose, right?",
                ],
                "channel": "npc",
                "enabled": True
            }, {
                "regex": ".*Crowne Memorial.*",
                "example": "Entering Crowne Memorial.",
                "toggle": "Snark",
                "channel": "system",
                "enabled": True,
                "append": [  # randomly selected
                    "Whats a little debt between friends.",
                    "Maybe you should go back to Atlas Park?",
                ],
            }
        ]
    }, {
        "prefix": "The",
        "enabled": True,
        "patterns": [
            {
                "regex": "The name.*",
                "example": "The name <color red>Toothbreaker Jones</color> keeps popping up, and these Skulls were nice enough to tell you where to find him. Time to pay him a visit.",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": ".* boosts the damage of your attacks!.*",
                "example": "The Just Chillin' boosts the damage of your attacks!",
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "bottom.*",
                "example": "The bottom of this empty box..",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "whiteboard.*",
                "example": "The whiteboard appears to be...",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            }
        ]                
    }, {
        "prefix": "Your",
        "enabled": True,
        "patterns": [
            {
                "regex": "combat improves to level (\\d+).*",
                "example":"Your combat improves to level (23)! Seek a trainer to further your abilities.",
                "toggle": "Speak Levelup",
                "channel": "system",
                "state": "level",
                "enabled": True
            }, {
                "regex": "Siphon Speed.*",
                "example": "Your Siphon Speed has slowed the attack and movement speed of Prototype Oscillator while increasing your own!",
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": "Darkest Night.*",
                "example": "Your Darkest Night reduced the damage and chance to hit of Fallen Buckshot and all foes nearby.",
                "soak": 10,
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }
        ]
    }, {
        "prefix": "Shutting",
        "enabled": True,
        "patterns": [
            {
                "regex": "off Darkest Night.*",
                "example": "Shutting off Darkest Night.",
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            } 
        ]
    }, {
        "prefix": "Something's",
        "enabled": True,
        "patterns": [
            {
                "regex": ".*",
                "example": "Something's not right with this spot on the floor...",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            } 
        ]
    }, {
        "prefix": "In",
        "enabled": True,
        "patterns": [
            {
                "regex": ".*",
                "example": "",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            } 
        ]
    }, {
        "prefix": "Jones",
        "enabled": True,
        "patterns": [
            {
                "regex": ".*",
                "example": "",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            } 
        ]
    }, {
        "prefix": "This",
        "enabled": True,
        "patterns": [
            {
                "regex": ".*",
                "example": "This blotch of petroleum on the ground seems fresh, perhaps leaked by a 'zoombie' and a sign that they're near. You take a photo and send it to Watkins.",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            } 
        ]
    }, {
        "prefix": "You've",
        "enabled": True,
        "patterns": [
            {
                "regex": ".*",
                "example": "You've found a photocopy of a highly detailed page from a medical notebook, with wildly complex notes about cybernetics. ",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            } 
        ]
    }, {
        "prefix": "Where",
        "enabled": True,
        "patterns": [
            {
                "regex": ".*",
                "example": "",
                "toggle": "Speak Clues",
                "channel": "system",
                "enabled": True
            } 
        ]
    }, {
        "prefix": "Congratulations!",
        "enabled": True,
        "patterns": [
            {
                "regex": ".*",
                "toggle": "Speak Badges",
                "channel": "system",
                "enabled": True
            }                
        ]
    }, {
        "prefix": "",
        "enabled": True,
        "patterns": [
            {
                "regex": ".* the team.*",
                "toggle": "Team Changes",
                "channel": "system",
                "enabled": True
            }, {
                "regex": ".*heals you with their Radiant Aura.*",
                "example": "Ghoblyn heals you with their Radiant Aura for 44.3 health points.",
                "strip_number": True,
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": ".*heals your with their Twilight Grasp.*",
                "example": "Old McFahrty heals you with their Twilight Grasp for 22.02 health points.",
                "strip_number": True,
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }, {
                "regex": ".*heals you with their Transfusion.*",
                "example": "Just Chillin' heals you with their Transfusion for 92.22 health points.",
                "strip_number": True,
                "toggle": "Speak Buffs",
                "channel": "system",
                "enabled": True
            }                    
        ]
    }
]


_patterns = None

def load_patterns():
        """
        Load all patterns from patterns.json
        """
        global _patterns
        
        if _patterns:
            return _patterns

        log.debug('Loading patterns...')
        if os.path.exists('patterns.json'):
            with open('patterns.json', 'r') as f:
                patterns = json.load(f)
                _patterns = patterns
                return patterns

        _patterns = DEFAULT_PATTERNS
        log.info('No patterns.json found, using default patterns.')
        return _patterns


def delete_pattern(prefix_name, pattern_name):
    """
    Delete a particular pattern from patterns.json
    """
    log.info(f"delete_pattern(self, {prefix_name}, {pattern_name})")
    all_patterns = load_patterns()
    for prefix in all_patterns:
        if prefix['prefix'] == prefix_name:
            for i, p in enumerate(prefix['patterns']):
                if p['regex'] == pattern_name:
                    log.info("deleting: %s", prefix['patterns'][i])
                    del prefix['patterns'][i]
                    log.info('Deleted pattern %s from prefix %s', pattern_name, prefix_name)
                    break
            else:
                log.warning('Pattern %s not found in prefix %s', pattern_name, prefix_name)
            break
    else:
        log.warning('Prefix %s not found', prefix_name)

    with open('patterns.json', 'w') as f:
        json.dump(all_patterns, f, indent=4)


def save_pattern(prefix_name, pattern_name, pattern, hindex=None):
    """
    Save a particular pattern to patterns.json
    """
    log.info(f"save_pattern(self, {prefix_name}, {pattern_name}, {pattern}, {hindex=})")
    all_patterns = load_patterns()
    for prefix in all_patterns:
        if prefix['prefix'] == prefix_name:
            if hindex is not None:
                # prefix['patterns'][hindex]['regex'] = pattern_name
                log.info('Replacing pattern at index %s in prefix %s', hindex, prefix_name)
                log.info('[NEW] %s', pattern)
                log.info(
                    'The prefix "%s" has %d patterns', prefix_name, len(prefix['patterns'])
                )
                try:
                    prefix['patterns'].insert(hindex, pattern)
                except IndexError:
                    if hindex == 1 + len(prefix['patterns']):
                        prefix['patterns'].append(pattern)
                    else:
                        log.error(
                            'Index %s is out of range for prefix %s with %d patterns',
                            hindex, prefix_name, len(prefix['patterns'])
                        )
                break
            else:
                for i, p in enumerate(prefix['patterns']):
                    if p['regex'] == pattern_name:
                        prefix['patterns'][i] = pattern
                        break
                else:
                    # this is a new pattern, sneaky.
                    log.info('Adding new pattern %s to prefix %s', pattern_name, prefix_name)
                    prefix['patterns'].append(pattern)
                break
    else:
        # this is a new prefix, super-sneaky.
        log.info('Adding new prefix %s with pattern %s', prefix_name, pattern_name)
        all_patterns.append({
            'prefix': prefix_name,
            'patterns': [pattern]
        })

    with open('patterns.json', 'w') as f:
        json.dump(all_patterns, f, indent=4)


def get_prefixes():
    """
    Get all prefixes from patterns.json
    """
    prefixes = []
    for prefix in load_patterns():
        prefixes.append(prefix['prefix'])
    return prefixes


def get_patterns(prefix):
    """
    Get all patterns for a given prefix from patterns.json
    """
    for pattern_prefix in load_patterns():
        if pattern_prefix['prefix'] == prefix:
            return pattern_prefix['patterns']
    return []


def get_pattern(prefix, pattern_name):
    for pattern_prefix in load_patterns():
        if pattern_prefix['prefix'] == prefix:
            for pattern in pattern_prefix['patterns']:
                if pattern['regex'] == pattern_name:
                    return pattern
    return None


def get_known_toggles():
    toggles = set()
    for prefix in load_patterns():
        for pattern in prefix['patterns']:
            if 'toggle' in pattern and pattern['toggle']:
                toggles.add(pattern['toggle'])
    return list(sorted(toggles))

