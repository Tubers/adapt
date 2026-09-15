RULE lifecycle/archive-folders - finished business. Nothing depends on it.
- An archive folder is a RECORD, not a task list. Picking up finished work as if pending is the failure this prevents.
- Do not read one looking for current state. The only task lists are TASKS.md files and a live handoff's next-steps section.
- Do not revive an archived piece of work without reading the owning project's history first: rules.py history <project>.
- Archived material stays unedited even where it turned out wrong. Corrections go in the history.
- Nothing here is imported or read by live code. Live code pointing into an archive is a bug: promote the file instead.
