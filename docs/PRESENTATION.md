# Clerkmark — live presentation kit (LexHack 2026 Awards Ceremony)

Third place. The ceremony is a live session where winners present and take questions.
This is the talk, the exact click path, the Q&A prep and the failure plan.

Every number below is on screen while you say it. If the screen says something different
on the day, say what the screen says. Never read a number off this page.

---

## Before you go live (10 minutes)

- [ ] Open `https://clerkmark.vercel.app/api/health` once, then run the sample once. This
      warms the serverless function so it is not cold on camera.
- [ ] Fresh browser window, no extensions, no bookmarks bar, notifications off at the OS level.
- [ ] Browser zoom so the memo fills the frame. 110–125% is usually right at 1080p.
- [ ] Open two tabs: tab 1 `https://clerkmark.vercel.app/` (the cover), tab 2 the repo.
- [ ] Have `Alt+Shift+P` in mind. It swaps to the recorded run if the live one stalls.
- [ ] Close this file and the editor. Share only the browser window.

---

## The 3-minute talk

**0:00 — the hook.** Tab 1, the cover on screen, do not scroll yet.

> In 2023 a New York lawyer filed a brief citing six cases that did not exist. He had
> asked a chatbot. That story is famous. What happened next is not: it kept happening,
> and mostly to people who have no lawyer at all.

**0:20 — the number.** Point at the "Why" line on the cover.

> Two thousand and seventy-nine court decisions have now found hallucinated or misquoted
> citations in filings. Eleven hundred and ninety-six of them involve someone representing
> themselves. Court staff find these by looking up every case by hand.

**0:35 — the product.** Click **Try the sample filing**.

> Clerkmark reads the filing, finds every citation, and looks each one up in a free law
> library. This is a synthetic filing built from a real sanctions case.

**1:00 — the result.** The memo paints, the stamp lands.

> Twenty-three citations, about four seconds. Every row carries the rule that decided it.

**1:10 — the heart of it.** Scroll to lines 8 and 9. Pause here. This is the whole pitch.

> Line eight is circled in red. Page 366 belongs to Greenleaf v. Garlock, and no case
> named Miller exists anywhere in that volume. So: likely not a real case.
>
> Line nine is in pencil. Not red. That one is a state citation the free library simply
> does not hold, so we cannot say anything about it.
>
> A naive checker prints "not found" for both of these. If intake staff read both as fake,
> the person who gets hurt is the filer who had no lawyer. Keeping those two apart is the
> product.

**1:45 — the evidence.** Click **[Show the page]** on line 6.

> And every call shows its work. The page this citation points at belongs to J.D. v. Azar.
> That is the reporter's own record, with links to the free files.

**2:00 — the honesty.** Click the **Evaluation** tab, scroll to the closing line.

> Twenty citations with known answers, scored on every run. Twenty of twenty correct.
> Zero of eleven real cases marked likely not real. That last number is the one we
> actually optimised for.

**2:20 — the obvious objection, answered with data.**

> We tested the question everyone asks: can you just paste this into a chatbot? We did,
> twice, same prompt. Fifteen and sixteen out of twenty, and the two runs disagreed on a
> quarter of the citations. It waved through a fabricated case and confirmed two quotes
> we had deliberately altered.

**2:40 — the limits.** Scroll the cover's Limits block, or say it from memory.

> It is United States only. The free library stops around 2019. It does not check
> statutes or pin pages. All of that is written on the page. It is a triage aid, not a
> finding.

**2:55 — close.**

> clerkmark.vercel.app. Code and the write-up are linked from it. Happy to take questions.

---

## The 5-minute version

Same spine, with two additions:

**After 1:45, add the misquote (about 40 seconds).** Scroll to line 16.

> Real case, wrong words. The filing quotes Chan v. Korean Air Lines. Three words differ
> from the opinion, and the memo marks which three. A citation checker that only asks
> "does this case exist" passes this row.

**After 2:20, add how it works (about 40 seconds).** Click **How it works**.

> The rule is deterministic and printed in full, right here. eyecite finds the citations.
> The Caselaw Access Project supplies the volumes, pages and opinion text. Plain Python
> decides the class. A model is optional, it only adds an advisory note on quoted rows,
> and it can never change a class. That was deliberate: the thing that decides whether
> someone's filing looks fabricated should be a rule you can read.

---

## Q&A prep

Answer in one or two sentences, then stop. The honest answer is the strong answer here.

**"Isn't this just a case law database?"**
> A database answers one lookup at a time and tells you nothing about a filing. Clerkmark
> reads all twenty-three citations, checks which case actually sits at each cited page,
> compares the quoted words to the opinion, and writes it up with the rule. The database
> is the input, not the product.

**"Can't I just ask ChatGPT or Gemini?"**
> We measured it rather than guessing. Same filing, same prompt, twice: fifteen and
> sixteen of twenty, and the two runs disagreed on a quarter of the rows. It called a
> fabricated case real and confirmed two altered quotes. A grounded model with search
> would do better. What it still cannot do is tell you whether a citation is missing
> because it was invented or because the free corpus stops in 2019. That is a fact about
> coverage, not about law.

**"What about Westlaw and Lexis? They have this."**
> They do, for lawyers checking their own drafts, on a paid subscription. We are on the
> receiving side, at the intake desk, on someone else's filing, using a free corpus. Many
> state trial courts and self-help centres do not have a seat for the person doing intake.

**"How is this different from Learned Hand?" (the AI clerk piloted in LA County)**
> Learned Hand is a broad paid chambers platform, and the citation checking I have read
> about verifies the orders the tool itself drafts. Clerkmark is free, does one thing, and
> runs on a document the court received.

**"Your corpus stops in 2019. Isn't that fatal?"**
> It is the biggest limitation and it is printed on the page. Recent real cases read "not
> in the free library", never "fake", which is the safe direction to fail. Adding a
> CourtListener token extends coverage, and that path is already built and tested.

**"What is your false positive rate?"**
> On the seeded set, zero of eleven real cases were marked likely not real. Be honest
> about what that is: twenty citations we chose, not a field study. The next step is
> running it against real filings from a court that will share them.

**"Did AI write this?"**
> Yes, and it is disclosed in the README. The code was written with AI coding assistants
> under my direction during the event. I can walk you through any module; the architecture
> and every design decision are documented in the repo.

**"Who would pay for it?"**
> Honest answer: I do not know yet, and I would rather say that than invent a number. The
> plausible buyers are state court administrative offices, self-help centres and legal aid
> organisations, and those are usually grant funded rather than subscription. Finding out
> is what I want to use the fellowship for.

**"What is next?"**
> CourtListener as a live second source so post-2019 cases resolve, then statutes, then a
> version of the memo written for the filer rather than the clerk, so a self-represented
> person can fix the brief instead of being sanctioned for it.

---

## If the demo breaks

1. **Live run stalls or errors.** Press `Alt+Shift+P`. The recorded run paints under a
   "Replay · run of 26 Sep 2026" banner. Say out loud: "this is the recorded run". Never
   present it as live.
2. **The site is down.** Share the 2-minute video instead: it is in your Downloads folder
   as `clerkmark_demo.mp4`, and shows the same path.
3. **Screen share fails.** The talk still works. Describe lines 8 and 9 and give the URL.
4. **Nothing works.** Say so plainly, give the URL, and take questions. People remember
   composure.

---

## Links to have pasted in the chat

```
https://clerkmark.vercel.app/
https://github.com/itssaharsh/clerkmark
```
