RULE repo/no-silent-changes - every lasting change to a folder is logged in its project's HISTORY.jsonl, whoever owns the folder.
- Lasting means it outlives the session: a file moved, renamed, deleted or created, a folder restructured, a script, data file or rule changed. Reading and scratch work are not.
- Log it in EVERY project it touches. A move is logged where the file left AND where it arrived: rules.py history add <folder> --kind change --title "<what changed>" --what "<old path> to <new path>".
- Folders that are not yours included. A change nobody logged cannot be told apart from a lost file.
- Log it before leaving that project, not at session end. The rule router reminds you once if you edit files in one project and move on to another with nothing logged; shell writes it cannot see.
- Why: a session resumed later runs rules.py history <folder> --since <date> and learns what moved, instead of acting on a layout that no longer exists.
