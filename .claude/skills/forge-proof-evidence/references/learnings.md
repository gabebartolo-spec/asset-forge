# Learnings log (forge-proof-evidence)

Only findings that proved effective on Asset Forge: a method that caught or prevented a real
defect, a recurring failure whose fix was verified (test, capture or green CI), or a measured
time saving. Each entry: `## YYYY-MM-DD · topic`, then **Finding**, **Evidence** (PR, commit, run
id, capture), **Lesson**. If a finding contradicts SKILL.md, fix SKILL.md instead of appending;
mark entries "promoted" once moved into it. A lesson that is true for every project goes to the
general skill's log instead (github-hygiene, game-architecture, art-qa-critic, ask-the-director,
ai-game-dev-playbook in ~/.claude/skills).

## 2026-10-20 · Read the real generated text, not just the tests
PR #12's mocked tests were green, but the lead reading the 10 real prompt outputs found the animal
template forcing "four legs clearly visible", so the robin prompt asked for a four-legged bird.
Fixed at 0a00768 with a test that no template states a limb count. Lesson: for template-driven
generation, read every real output once per type, and keep fixed template text free of anything
that belongs to the user's input (counts, colours, parts).
