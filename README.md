# GRE Vocab Quiz Slides

Daily quiz carousels for [@gre_vocab_cartoons](https://www.instagram.com/gre_vocab_cartoons/).

- `slides/` — 1,206 quizzes (#470–#1675): `NNNN-word-q.jpg` (question) and `NNNN-word-a.jpg` (answer cartoon), built from the vincekotchian.com media library
- `queue.json` — quiz order, options, answers, captions
- `post_next.py` — posts the next quiz via the official Instagram API (needs `IG_TOKEN` env var; never commit tokens)

## Daily posting

`.github/workflows/daily-quiz.yml` runs every day at 15:53 UTC (8:53 am Pacific in daylight time) and can also be run by hand from the **Actions** tab ("Run workflow"). It needs one repository secret, `IG_TOKEN`, holding the Instagram API token. Each run appends a line to `posted.log`. On Sundays it also refreshes the token's 60-day expiry.

## Daily Reel

`.github/workflows/daily-reel.yml` posts one Instagram Reel per day at 00:47 UTC (5:47 pm Pacific in daylight time, 4:47 pm after clocks fall back), using the same ~16-second 1080x1920 quiz video as the YouTube Shorts (`make_short.py`). It uses the same `IG_TOKEN` secret and the official Instagram API only.

- **Order:** Reels work through `queue.json` from the end (#1675, #1674, ...), while carousels and Shorts count up from #471, so followers never see the same word twice in one day. Any number that already appears in a carousel caption ("Pop quiz #N:") among the 50 most recent media is skipped.
- **Safety:** at most one Reel per 16 hours, never a quiz number that already has a Reel (checked against the account's recent "Reel quiz #N:" captions and `reels.log`), and the script stops on any API error with no retry loops.
- **Hosting:** each run force-pushes an orphan branch, `reel-files`, holding only that day's `NNNN.mp4` (one commit, replaced every run, so the repo never grows). Instagram fetches the video from `raw.githubusercontent.com/wkotchian/gre-vocab-quiz-slides/reel-files/NNNN.mp4`.
- **Log:** each run appends its POSTED REEL / SKIP / QUEUE EMPTY / TEST OK line to `reels.log`.
- **Test flag:** run the workflow by hand with `test_container=true` (or `post_reel.py --test-container`) to render, host and build the Instagram container up to FINISHED without publishing anything. `num` overrides the quiz number; `check=true` is a read-only check (lists recent Reels and the publishing limit, and runs `post_next.py --dry-run`).

## Weekly stats (read-only)

`.github/workflows/weekly-stats.yml` runs `stats.py` every Sunday at 14:17 UTC (and on demand from the Actions tab). It never posts or edits anything. It reads Instagram followers plus each post's views, reach, likes, comments, saves, shares and (Reels) average watch time, and YouTube subscribers plus each upload's views, likes and comments, for everything published since 2026-10-15. Results go to `stats/YYYY-MM-DD.json`, `stats/posts.csv` (one row per post per run) and `stats/accounts.csv`. Posts are labeled with their quiz number and word from the posting logs. A Claude scheduled task reads `stats/` on Monday mornings and reports to Vince.

## Daily GRE Quant Short (YouTube only)

`.github/workflows/daily-math-short.yml` uploads one GRE Quant Short per day at 02:23 UTC to the same YouTube channel, using the `YT_*` secrets. Questions come from GRE Math Knight 2.0: `build_math_queue.py` builds `math_queue.json` (775 phone-legible items: 388 questions, then 387 fresh versions), and `make_math_short.py` renders a 44-second video (question, 30-second countdown with a pause hint, answer, short solution, one trap answer with its mistake, end card).

- **Start gate:** nothing uploads until `math/start_date.txt` holds a date (YYYY-MM-DD). Set it the day GRE Math Knight 2.0 is live, since the end card describes 2.0.
- **Safety:** at most one per 16 hours; never re-uploads a number already on the channel (titles "GRE Quant #N") or in `math_shorts.log`.
- **Test:** run the workflow by hand with `render_only=true` to render one video and upload nothing.
- No Instagram Reels for these (Vince, 2026-11-18: pausing a Reel is too awkward).

## Daily SAT Math Short (YouTube only)

`.github/workflows/daily-sat-short.yml` does the same for SAT Math Swordsman (`upload_math_short.py --app sat`, `sat_queue.json` from `build_sat_queue.py`, titles "SAT Math #N", log `sat_shorts.log`) at 23:17 UTC. Gated by `math/sat_start_date.txt` (set the day SAT Math Swordsman is live). `check_fit.py gre|sat` drops items that won't fit on screen; run it after rebuilding a queue.

## Daily ACT Math Short (YouTube only)

`.github/workflows/daily-act-short.yml`: same setup for ACT Math Adventurer (`--app act`, `act_queue.json` built with `build_sat_queue.py act ...`, titles "ACT Math #N", log `act_shorts.log`) at 16:37 UTC. Gated by `math/act_start_date.txt`.
