# A project doc's shape

Built with `living-doc` (its conventions still apply: provenance, the naming contract, the
glossary, the budget). A project doc adds the project's live state: what is happening now,
what waits on Meri, what was decided, what must hold, and how the code will be shaped.
History lives only in Activity.

## Front and back

Front tabs are what Meri reads; each stays short enough to skim. Back tabs are Claude's
working space; she opens them only to dig in. Anything she does not need to see every time
goes to the back, and the front links to it.

| | Tab | Holds | Order |
|---|---|---|---|
| Front | Overview | Goal in one sentence, the header, Needs you, Claude decided (check me) | `a0` |
| Front | One tab per feature | Decided behavior, Invariants, What it looks like, Open questions, considered options last | `a1`, `a3`, ... |
| Front | `<Feature>` shape | The code plan, right after its feature tab | `a2`, `a4`, ... |
| Front | PRs and tickets | The PR map | after the features |
| Back | Findings | Every finding, all three tags | first back tab |
| Back | Workbench | Standing rules, Handy facts, evidence notes, what each background agent was asked | |
| Back | Background | Explainers she asked for, one section each | |
| Back | Activity | One dated row per sweep: what changed, where, threads answered, corrections | second to last |
| Back | Glossary | Every term that is not plain English | last |

Start with Overview, one feature tab with its shape tab, PRs and tickets, Findings,
Workbench, Activity and Glossary. Add tabs as the project grows; never split one short
subject across tabs.

## Overview (front)

Fits on one screen. Top to bottom:

1. **Header**: a table, readable at a glance.

   | | |
   |---|---|
   | Now | The one thing being worked, with a link to its tab |
   | Running | Each background agent or unattended run: what, started, state (running, landed, pushed, failed) |
   | Waiting on you | How many Needs you rows, and the first one |
   | Invariants | Per feature: how many hold, broken, recheck, not checked |
   | Later | Parked items and "remind me later" asks |

2. **Needs you**: numbered, easiest first. Columns: #, Question (plain words), What it
   affects, Claude's lean. Things only Meri can do (run a prod query, look at a screen, ask
   someone) go here too, marked "you check". She answers by number in one comment.
3. **Claude decided, check me**: calls Claude made without asking (unattended runs, or when
   told to decide). Columns: The call, Why, How to undo. A row stays until she accepts or
   overturns it; accepted rows move to Decided behavior.

## Feature tab (front)

- **Decided behavior**: a two-column table (Topic, What happens). Only settled calls. The
  reasons live in the thread or a Because column, whichever she prefers.
- **Invariants**: the conditions the feature must meet to be done. Opened at Start with a
  first draft from the goal and whatever is already decided, even if only three rows.
  Columns: #, Invariant (one plain, checkable sentence: "a paused rule keeps its action"),
  Why, Status (Holds, Broken, Recheck, Not checked), Evidence (test, query and result,
  screenshot, PR link), Last checked. Rules:
  - Every decision is checked for a condition it adds, changes or drops, and this table is
    updated in the same pass.
  - A row is Holds only with evidence. Without it, it is Not checked.
  - When a PR the Evidence points at gets new commits, the row goes to Recheck.
  - The feature is done only when every row holds. Broken and Not checked rows count as
    needed now to finish.
- **What it looks like**: a concrete picture of the result, because a visual reader judges
  behavior by seeing it.
  - Tables show the full state: every column, plus a plain-meaning column next to names
    she cannot be expected to remember.
  - A proposal is drawn at the same detail as the current state it replaces, side by side.
    "Current" means production, never an earlier draft.
  - Behavior is told as a scenario timeline ("a new document arrives", "Monday: ...,
    Wednesday: ...").
  - A screenshot of the running UI sits next to the decision it shows, when there is a UI.
  - A diagram for any flow with more than two steps; none for decoration.
- **Open questions**: Question, Why it matters, Route (Codebase, Prod data, Web, Ask Claude
  here, Parked). An answered row moves into Decided behavior or Not in the first version.
- **Not in the first version**: deferred scope, as a bullet list.
- **Considered options**: last, each with a Decided or Later line.

## Shape tab (front)

The code plan, written and agreed before any code. The structural review happens here, on a
page of pseudocode, instead of on a finished PR. This tab uses code names and pseudocode;
the "no deep specifics" voice rule does not apply to it.

1. **The change in three sentences.**
2. **Where things live**: Piece, Lives in, New / Changed / Deleted, Owns (one line). Name the
   service classes and their entrypoints.
3. **Types**: each new or changed type, enum and table, as pseudocode with a one-line meaning
   per field.
4. **Flow**: pseudocode per main path, 10 to 30 lines each, using the names from the table. A
   mermaid sequence diagram when more than three pieces talk.
5. **Reused, not rebuilt**: existing pieces this leans on.
6. **Deleted**: what goes away (old paths, shims, dead fields).
7. **Structure check**: the `jonathan-review` checks run against the shape (one service per
   capability, one entrypoint, no shims, typed everything, enums not strings, config not
   constants, consistent names). Each finding is fixed in the shape before code.
8. **PR slices**: how the shape splits into PRs; each slice becomes a row in PRs and tickets.
9. **Considered shapes**: each with a Decided or Later line.

Implementation starts only after Meri approves the shape in a comment. When implementation
departs from it, update this tab in the same pass; a real design change goes to Needs you
first.

## PRs and tickets (front)

One table in merge order. Columns: Order, PR (link), What it's for (one plain line), Pairs
with, Ticket (link), State (draft, in review, approved, CI red or green, merged), Needed to
finish (Now or Can wait). Every sweep refreshes State (`references/sweep.md`, step 1) and
flags merged PRs, tickets whose PRs are all merged (candidates to close) and new PRs on the
project's branches.

## Findings (back)

Every problem a review, run or investigation turns up. Columns: Finding (plain words), Cause
(we caused it or already there), Why it matters to the goal, Needed to finish (Now or Can
wait), Where (tab or PR). Can wait rows are also listed under the feature's Not in the first
version. A Now row that needs her call goes into Needs you; the rest Claude fixes.

## Workbench (back)

- **Standing rules**: project-wide rules she has set: scope ("one PR for the whole cleanup"),
  risk ("a few minutes of downtime is fine"), names. Checked before every proposal.
  Conditions the feature itself must meet go in its Invariants table, not here.
- **Handy facts**: commands, local URLs, account names, which site PR pairs with which server
  PR. Never passwords, tokens or keys: the doc is shared. Say where the secret lives instead.
- **Evidence notes**: queries, outputs and file references that back a Decided, Invariants
  or Findings row, when they are too long for its Evidence cell.
- **Agent handoffs**: what each background agent was asked, one row each.

## Current state only

The doc body reads as the plan as it stands. No "used to be", no "we switched from", no list
of what Claude got wrong, no rejected alternative written as if it were the plan. Considered
options keep their Decided or Later line. Corrections go in the thread and in Activity.

After any decision or correction, walk every later section and every tab that depends on it
(Invariants and the shape tab included) and update them in the same pass.

## Overview upkeep

Every sweep that changed anything brings the header, Needs you and the PR map current in the
same pass. When Now empties, the top Later item is named in the sweep's chat line. A stale
Overview is the first thing that breaks trust.
