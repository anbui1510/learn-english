# Karaoke accessibility checklist (NFR-06)

Manual checks for the learner karaoke player in `LearnerPanel`.

1. **Keyboard-only line navigation**  
   Tab into the karaoke region (focus ring visible). Press `←` / `→` to change
   lines; `Home` / `End` jump to first / last. Confirm keys do not fire while a
   text input elsewhere has focus.

2. **Native audio controls**  
   Tab to the `<audio>` element and play / pause with the keyboard.

3. **Screen reader spot check**  
   With NVDA, VoiceOver, or TalkBack: changing lines announces via the live
   region (speaker + line text). Red-word buttons expose “Replay AI sample for …”.

4. **Contrast**  
   Active karaoke word uses dark teal (`bg-teal-800`) on white text (≥4.5:1).
   Red / amber / green score words use darker text tokens for readability.

5. **Speed + VI controls**  
   Speed slider and “Show VI gloss” have associated labels (`htmlFor` / `id`).
