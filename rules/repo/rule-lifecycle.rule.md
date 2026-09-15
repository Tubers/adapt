RULE repo/rule-lifecycle - how a rule is observed, created, changed and deleted.
- OBSERVE: a rule the router injects is compulsory, not advice. It arrives when a gate in rules/INDEX.md matches the path or command you touch: once per session, and again, marked CHANGED, if its text was edited since. No reload is ever needed.
- CREATE: a new rule starts as a parked candidate and is approved past one embedding pass: writing/rule-candidates. Write the file, add its gate line to rules/INDEX.md, then rules.py decide <id> approve.
- CHANGE: edit the rule file. ask_rule_approval.py asks the user first unless the last rules.py audit flagged that rule. A new rule and every approval always ask.
- MOVE or RENAME: rules.py move <rule> <new-name>. It rewrites every reference: index, rules, READMEs. Never mv a rule by hand.
- DELETE: ask the user first. Then remove the file AND its gate line, log it (repo/no-silent-changes), and run rules.py reconcile: a dead gate or orphan is a defect.
- IMPROVE the set, not one rule: rules.py audit prints redundancy, filing, hub and gate findings in the order to act on them.
- Cap, shape and register: writing/readme-and-rules, writing/compressed-register. Every command: rules.py help.
