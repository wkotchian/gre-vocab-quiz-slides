# GRE Vocab Quiz Slides

Daily quiz carousels for [@gre_vocab_cartoons](https://www.instagram.com/gre_vocab_cartoons/).

- `slides/` — 1,206 quizzes (#470–#1675): `NNNN-word-q.jpg` (question) and `NNNN-word-a.jpg` (answer cartoon), built from the vincekotchian.com media library
- `queue.json` — quiz order, options, answers, captions
- `post_next.py` — posts the next quiz via the official Instagram API (needs `IG_TOKEN` env var; never commit tokens)

## Daily posting

`.github/workflows/daily-quiz.yml` runs every day at 15:53 UTC (8:53 am Pacific in daylight time) and can also be run by hand from the **Actions** tab ("Run workflow"). It needs one repository secret, `IG_TOKEN`, holding the Instagram API token. Each run appends a line to `posted.log`. On Sundays it also refreshes the token's 60-day expiry.
