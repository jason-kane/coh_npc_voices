"""
Take all the files in raw_data (entities downloaded from https://cod.uberguy.net/html/index.html)
and cut out all the stuff we do not need.  I also removed index.json.

Why do this? 19.4 MB -> 1.16 MB

I don't have any way to know how many of these can talk, or what they might say.
But we once we get a message from them, we can find them reasonably quickly to
determine the group (like 5thColumn) and gender (GENDER_MALE) and use that as
the basis for creating the voice that should be used.  

Output is a json file with a bunch of entries like:
{
...
  "Colonel": {
    "description": "Nemesis' officers are some of the best trained soldiers in the world, and they show amazing discipline and devotion to their master. They're armed with the Nemesis lance, a long rifle that can also operate effectively as a spear. Their skill with this weapon makes them deadly at any distance.",
    "gender": "GENDER_MALE",
    "group_name": "Nemesis"
  },
...
}
"""
import os
import json

def main():
    output = {}
    for filename in os.listdir("raw_data"):
        with open(os.path.join("raw_data", filename), "r") as infile:
            raw = infile.read()
            parsed = json.loads(raw)

            gender = parsed.get("gender")
            if gender is None:
                print(f'Entity {filename} has no gender')

            group_name = parsed["defaults"].get('group_description')
            if group_name in [None, '']:
                group_name = parsed['group_name']
            description = parsed["defaults"].get('description', '')

            for variant in parsed["levels"]:
                for name in variant["display_names"]:
                    if name in output:
                        print(f'Multiple entries with display name: {name}')
                    else:
                        output[name] = {
                            "gender": gender,
                            "group_name": group_name,
                            "description": description
                        }

    with open('all_npcs.json', 'w') as outfile:
        outfile.write(
            json.dumps(
                output, 
                indent=2,
                sort_keys=True
            )
        )

if __name__ == '__main__':
    main()