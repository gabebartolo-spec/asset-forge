# How to ask the director a question

The director's standing instruction: *ask me explicit questions rather than pondering my meaning;
speak in direct terms about the game impact, not the technical detail; and if the question is
about a visual element, show me clearly labelled images as I read it.* Every agent follows this.

## When to ask

Ask the moment the next step depends on a judgement that is the director's: anything the player
sees, decides, feels or pays for; anything that spends money; anything that changes a decision
already in `DECISIONS.md`; any look. Do not ask about things the pack already answers, and do not
ask the director to choose between technical implementations that produce the same game.

Never park a question inside a progress report. Never guess at a visual. Never delay a merge
because a question was not asked.

## The format

Use the `AskUserQuestion` tool when it is available; otherwise write the same structure in the
message. At most four questions per message. Each question:

1. **One decision.** Not "thoughts on the battle UI?" but "Should the enemy's weapons be visible
   before the fight starts?"
2. **Game impact first, in plain words.** What the player will experience under each option. No
   file names, no class names, no numbers unless the number is the thing being chosen.
3. **Recommended option first, marked (Recommended),** with one line on why.
4. **Every option has its cost or trade-off in one line.**
5. **Visual questions carry labelled images in the same message.** Label options A/B/C in the
   image itself (large text, top-left), show them at the size the game will show them, side by side,
   and include a 2× crop if detail matters. Anything that moves gets a 3-second clip, not a contact
   sheet.
6. **Say what happens if there is no answer** ("the branch waits" or "I proceed with A and it is
   reversible").

## Example (good)

> **Should a surgeon's failed roll be able to kill the patient?**
> - **Yes, rarely (Recommended).** Surgery becomes a real decision; deaths on the table become
>   stories. Cost: some players will feel robbed; the odds must be shown before they choose.
> - No, only maim. Safer, but the choice to operate loses weight.
> - No answer: I build "yes, rarely" behind a data flag; flipping it is a one-line change.

## Example (bad)

> I've been thinking about the injury system and there are a few ways we could go. One approach
> would be to model surgery as a skill check with a failure table that includes death, which has
> implications for `Injury.gd` and the save schema…

## After the answer

Write the answer in full under "Board and log" in the PR that acts on it (as `D-TBD-<slug>`, with
the date and the question id); the merge role records it in `docs/DECISIONS.md` at merge. If the director's answer conflicts with the pack, say so in one paragraph, propose
the better option, then do what the director decides.
