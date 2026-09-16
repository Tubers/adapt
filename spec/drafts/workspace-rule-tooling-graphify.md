Draft of a rule for the Adapt workspace, not a rule of this repository. It is kept here, under a
name that no rules router in this repository reads, until the workspace exists. It is mined from
the two instruction files `graphify install --project --platform claude` writes (0.9.63), and from
its hooks reference. On install, the rule between the markers becomes
`rules/tooling/graphify.rule.md` in the workspace, gated on the code files of each code
specialist's own skill copy (spec task t63 owns how that gate reaches a path outside the
workspace).

--- rule text ---
RULE tooling/graphify - query the code graph before reading or grepping your skill's code; refresh it after changing code.
- The graph for your skill is graphify-out/graph.json in your home folder. Pass --graph <that path> to every command; pass --out <your home> to every build.
- Before a codebase question: graphify query "<question>". Relationships: graphify path "<A>" "<B>". One concept: graphify explain "<concept>". Each returns a scoped subgraph, far smaller than grep output or GRAPH_REPORT.md.
- Before changing a symbol: graphify affected "<symbol>" shows what the change reaches.
- If graphify-out/wiki/index.md exists, navigate by it instead of browsing raw source.
- Read graphify-out/GRAPH_REPORT.md only for a broad architecture review, or when query, path and explain fall short.
- After modifying code: graphify update <your copy> --out <your home>. AST only, no model, no API cost.
- Asked for /graphify: load .claude/skills/graphify/SKILL.md before doing anything else.
--- end ---

Source text, as graphify wrote it, for comparison when graphify is upgraded:

Root instruction file:

    ## graphify

    This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

    Rules:
    - For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
    - If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
    - Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
    - After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

Instruction file under .claude/:

    # graphify
    - **graphify** (`.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
    When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Hooks registered in .claude/settings.json:

    PreToolUse, matcher "Bash|Grep": graphify hook-guard search   (timeout 10)
    PreToolUse, matcher "Read|Glob": graphify hook-guard read     (timeout 10)

What the hook-guard does, from its source: it reads the tool call, and when a fresh in-project
graph exists it adds a nudge toward `graphify query` as additional context. It never blocks,
except in the opt-in `--strict` mode, which denies the first raw read of indexed code once per
session. It ignores reads of files outside the project.

Added by the rule above and not in graphify's own text: the `affected` line, and the instruction
to pass --graph and --out, both because Adapt keeps the graph in the specialist's home rather than
beside the code.
