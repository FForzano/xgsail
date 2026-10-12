---
target: diary screen
total_score: 19
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
target_identity: "file:/Users/federico/Documents/Personal-DEV/xgsail/frontend/src/pages/diario/MyDiaryPage.tsx"
target_fingerprint: "sha256:e03986b933f37a72288d340f7cef7145b1bd01e116f17712d8dd1cfef941fd11"
target_path: /Users/federico/Documents/Personal-DEV/xgsail/frontend/src/pages/diario/MyDiaryPage.tsx
timestamp: 2026-10-12T13-18-42Z
slug: frontend-src-pages-diario-mydiarypage-tsx
closed: true
---
Method: dual-agent (A: design review, opus · B: detector, haiku). Browser visualization skipped: no browser tool in session; source-only review.

# Diary (MyDiaryPage) — 19/40 (Poor)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 2 | Failed feed query renders "Nessuna attività." — no error state (MyDiaryPage.tsx:51–62; useDiaryFeed exposes only isLoading) |
| 2 | Match system / real world | 2 | "Le mie attività", "Uscita" badge on every card, "Privata" meaning "mine", filter "all" option shown as "—" |
| 3 | User control and freedom | 2 | Checklist dismiss permanent, no undo |
| 4 | Consistency and standards | 2 | Nav "Diario/Logbook" vs tab "Le mie attività/My activities"; upcoming date uses success colour as decoration; English aria "Options" |
| 5 | Error prevention | 2 | Type filter ignores regattas (useDiaryFeed.ts:41–45, 87–95) |
| 6 | Recognition rather than recall | 2 | Import behind unlabeled ⋮ with one item; cards don't show activity type |
| 7 | Flexibility and efficiency | 1 | No search, date jump or boat filter — only infinite scroll |
| 8 | Aesthetic and minimalist design | 2 | Two badges for one fact; up to 5 callouts above the feed |
| 9 | Error recovery | 1 | No error UI or retry; offline marina = "you have no outings" |
| 10 | Help and documentation | 3 | Guided tour with demo cards + checklist |

Design specificity: generic social-card skeleton, with authored details (track as hero + photo inset, seasonal month bars, live "record too" banner). Cards carry no sailing data or people — Activity type has no summary stats. Club life absent from home tab.

Cognitive load: 5/8 fail (high): single focus (banners + live + up to 5 callouts + toolbar + checklist before card 1), chunking (LIMIT=5 callouts), hierarchy (callouts, checklist, cards same weight), one thing at a time (4 equal primary CTAs), minimal choices.

Strengths: track-as-hero with photo inset (EventRow.tsx:78–139); checklist/progress arbitration and seasonal bars; LiveRecordingBanner.

Priority issues:
- [P1] Feed card has no sailing data or crew → batch-prefetched summary (distance, duration, max SOG, mean TWS, crew avatars); drop "Uscita" badge. bolder, layout.
- [P1] Network failure renders as empty logbook and re-arms "record your first outing" → isError/refetch, offline banner, cached feed. harden.
- [P1] First mobile viewport crowded out → one-row "Prossimo:" upcoming, max one app banner, latest outing as hero. distill.
- [P2] Find/import weak; filter "—" and ignores regattas; no month headers or search. clarify.
- [P2] Media link has no accessible name and duplicates tab stop; 24px checklist dismiss; hover-only feedback. adapt.

Persona red flags: Casey — controls at top, 34px ⋮, no press state, regatta toggle jumps list. Jordan — 4 equal CTAs, "Associa un dispositivo" implies hardware needed, bare empty state, permanent dismiss. Giulia — "Pomeriggio - 12 ottobre" with no numbers, club life on another tab, "A bordo" says nothing about whose boat, "Privata" reads as a setting.

Minor: regattas tick "first outing"; absolute timestamps; 0.68rem progress labels; violet map token as placeholder decoration; no end-of-feed marker.

Questions: latest outing as a mini-analysis hero? One merged feed with club activity instead of two tabs? A logbook grouped by weekend with conditions as the header?
