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
