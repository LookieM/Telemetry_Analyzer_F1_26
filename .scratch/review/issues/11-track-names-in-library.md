# 11: Library and session headers still show raw track names (Track42, Austria, Catalunya)

**Status:** ready-for-agent
**Area:** debrief / library · bug · severity low

**What happens:** Planner and Setups show catalogue names (Madring, Spielberg, Barcelona) but the Library filter and table and the session header show the stored raw names: "Track42", "Austria", "Catalunya" (`screens/library.png`, `/session/48/laps` "#48 · Track42"). The same track appears under two names depending on the page.

**Fix:**
- [ ] normalise the track name in `/api/sessions` and `/api/sessions/{id}` payloads (or at import + one-off update of the `sessions.track` column with a backup)
- [ ] Library track filter lists catalogue names

## Comments
