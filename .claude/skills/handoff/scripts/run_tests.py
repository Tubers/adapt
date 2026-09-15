"""Tests for the handoff record. Builds its fixtures in a temp folder; reads nothing from the repo.

    python .claude/skills/handoff/scripts/run_tests.py
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import handoff_data as hd                                                     # noqa: E402
import handoffs                                                              # noqa: E402

PASS = FAIL = 0
NAME = "HAND" + "OFF.md"


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % label)
    else:
        FAIL += 1
        print("  FAIL  %s   %s" % (label, detail))


def point_at(tmp):
    """Aim the module at a throwaway data folder, the way a test repo would look."""
    hd.DATA = hd.ARCHIVE = os.path.join(tmp, "data")
    hd.LOG = os.path.join(hd.DATA, "log.jsonl")
    hd.REPO = tmp
    os.makedirs(hd.DATA)


def test_naming():
    print("occasion naming")
    check("a scope becomes a slug", hd.slug("Rule Mining!") == "rule-mining", hd.slug("Rule Mining!"))
    check("an empty scope is not silently empty", hd.slug("") == "unscoped")
    check("an occasion is date plus slug",
          hd.occasion_id("2026-09-10", "Rule Mining") == "2026-09-10-rule-mining")
    check("an occasion splits back", hd.split_occasion("2026-09-10-rule-mining")
          == ("2026-09-10", "rule-mining"))
    check("a folder that is not an occasion is rejected", hd.split_occasion("notes") is None)


def test_states(tmp):
    print("states, and what each one means")
    occ = "2026-09-10-rule-mining"
    d = hd.occasion_dir(occ)
    os.makedirs(d)
    open(os.path.join(d, hd.HANDOFF_FILE), "w").write("body\n")
    check("a handoff alone is retired", hd.state(occ) == hd.RETIRED, hd.state(occ))
    check("it is listed", [o["occasion"] for o in hd.occasions()] == [occ])
    check("nothing is pending yet", hd.pending() == [])

    open(hd.review_file(occ), "w").write("feedback\n")
    check("a review makes it PENDING", hd.state(occ) == hd.PENDING, hd.state(occ))
    check("pending lists it", [p["occasion"] for p in hd.pending()] == [occ])
    check("but no author is known yet", hd.pending()[0]["author_session"] is None)

    hd.append({"event": "written", "occasion": occ, "date": "2026-09-10",
               "session": "sess-1", "ts": "2026-09-10T22:48:00"})
    check("the log supplies the author", hd.pending()[0]["author_session"] == "sess-1")

    open(hd.response_file(occ), "w").write("reply\n")
    check("a response CLOSES it", hd.state(occ) == hd.CLOSED, hd.state(occ))
    check("closed occasions are not pending", hd.pending() == [])


def test_author_fallback(tmp):
    print("author lookup")
    hd.append({"event": "written", "occasion": "", "date": "2026-09-05",
               "path": "mechanics/inventory/" + NAME, "session": "sess-old", "ts": "x"})
    rec = hd.author_of("2026-09-05-inventory")
    check("a record with no occasion still matches on its date",
          (rec or {}).get("session") == "sess-old", rec)
    check("an unknown date finds nobody", hd.author_of("2001-01-01-nothing") is None)


def test_cli(tmp):
    print("the commands a reader actually runs")
    live = os.path.join(tmp, NAME)
    with open(live, "w", encoding="utf-8") as f:
        f.write("---\nskills: none\ndate: 2026-09-11\nscope: widgets\n---\n\nbody\n")

    check("retire needs no arguments beyond the path",
          handoffs.cmd_retire([live]) == 0)
    occ = "2026-09-11-widgets"
    check("the occasion came from the file's own front matter",
          os.path.isfile(os.path.join(hd.occasion_dir(occ), hd.HANDOFF_FILE)))
    check("the live file is gone", not os.path.isfile(live))
    check("retiring twice is refused", handoffs.cmd_retire([live]) == 2)

    check("draft opens a review", handoffs.cmd_draft([occ]) == 0)
    check("the review is inside the occasion folder", os.path.isfile(hd.review_file(occ)))
    check("the draft names the occasion",
          occ in open(hd.review_file(occ), encoding="utf-8").read())
    with open(hd.review_file(occ), "a", encoding="utf-8") as f:
        f.write("\nwhat the reader actually wrote\n")
    check("drafting again leaves what the reader wrote alone",
          handoffs.cmd_draft([occ]) == 0
          and "what the reader actually wrote" in open(hd.review_file(occ), encoding="utf-8").read())

    reply = os.path.join(tmp, "reply.md")
    open(reply, "w").write("answered\n")
    check("respond files the reply", handoffs.cmd_respond([occ, reply]) == 0)
    check("the occasion is closed", hd.state(occ) == hd.CLOSED)
    check("responding twice is refused", handoffs.cmd_respond([occ, reply]) == 2)
    check("an unknown occasion is refused", handoffs.cmd_respond(["2001-01-01-x", reply]) == 2)

    check("create with no scope explains the job rather than erroring",
          handoffs.cmd_create([]) == 0)
    check("create prints boilerplate carrying the occasion", handoffs.cmd_create(["widgets"]) == 0)
    made = os.path.join(tmp, "fresh", NAME)
    check("create writes the file", handoffs.cmd_create(["widgets", made]) == 0)
    text = open(made, encoding="utf-8").read()
    check("it opens with front matter", text.startswith("---\nskills:"))
    check("it carries scope and date", "scope: widgets" in text and "date: " in text)
    check("it tells the reader how to answer back", "draft" in text and "retire" in text)
    check("create refuses to overwrite", handoffs.cmd_create(["widgets", made]) == 2)


def test_check_command(tmp):
    print("check")
    # The hook logs this at write time; the fixture wrote the file directly, so supply it here.
    hd.append({"event": "written", "occasion": "2026-09-11-widgets", "date": "2026-09-11",
               "session": "sess-2", "ts": "2026-09-11T09:00:00"})
    check("a tidy record is clean", handoffs.cmd_check([]) == 0)
    loose = os.path.join(hd.ARCHIVE, "HAND" + "OFF-2026-01-01.md")
    open(loose, "w").write("stray\n")
    check("a loose handoff is reported", handoffs.cmd_check([]) == 1)
    os.remove(loose)
    stray = os.path.join(hd.occasion_dir("2026-09-11-widgets"), "notes.md")
    open(stray, "w").write("x\n")
    check("an unexpected file in an occasion is reported", handoffs.cmd_check([]) == 1)
    os.remove(stray)
    check("clean again", handoffs.cmd_check([]) == 0)


def main():
    tmp = tempfile.mkdtemp(prefix="handoff_data_test_")
    try:
        point_at(tmp)
        test_naming()
        test_states(tmp)
        test_author_fallback(tmp)
        test_cli(tmp)
        test_check_command(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
