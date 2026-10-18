# GRE Vocab Quiz Slides

Daily quiz carousels for [@gre_vocab_cartoons](https://www.instagram.com/gre_vocab_cartoons/).

- `slides/` — 1,206 quizzes (#470–#1675): `NNNN-word-q.jpg` (question) and `NNNN-word-a.jpg` (answer cartoon), built from the vincekotchian.com media library
- `queue.json` — quiz order, options, answers, captions
- `post_next.py` — posts the next quiz via the official Instagram API (needs `IG_TOKEN` env var; never commit tokens)
