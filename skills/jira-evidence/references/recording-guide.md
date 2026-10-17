# Recording guide

Guide the user through one `VIDEO` row at a time, in matrix order. Write each whole guide, headings included, in the conversation language. Send the next guide after the user says the previous clip is saved.

Each guide has exactly these parts, in this order:

```text
AC-2 · User edits the display name and sees a confirmation     depends on: AC-1 (profile page open)
File: raw/AC-2.mp4
Before recording: profile page open as the test user; note the current display name; mouse clicks shown (macOS: ⌘⇧5 → Options → Show Mouse Clicks)

● Start recording
  1. Open the display-name editor        → the name field becomes editable
  2. Type "QA Test 0216" and save         → a confirmation appears
■ Stop recording about 2 s after the confirmation and the new name are both visible

Reviewer must see: the confirmation and "QA Test 0216" as the profile's display name
```

- **Before recording** states the starting screen, the test data, the state the dependency leaves, and that mouse clicks are shown, so no change looks like it happened by itself.
- Every step is one user action, then `→` and what appears on screen. The last result is the row's `Expected proof`.
- When the proof is that something stays the same (a draft survives a reload, a retry changes nothing), make the reload or teardown its own step with its own visible result, then show the unchanged state in the next step.
- Quote UI labels that come from the AC text, the source code, or the user. Describe any other control by its role, as in "the avatar menu's profile option".
- **Stop recording** names the visible result that ends the clip.
- **Reviewer must see** becomes the `--expected` text when you compose the clip.
