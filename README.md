# Selected Hymns 詩歌選集

The text of the hymnal, kept as data so that it can be published in more than
one way. 848 hymns, English and Traditional Chinese together.

## The data

`data/N.md` — one Markdown file per hymn, numbered as the hymnal numbers them.
This is the source everything else is built from, and the one thing here that
is carried in git.

It is a lossless projection of the canonical YAML collection in
[`selected-hymns`](https://github.com/ickc/selected-hymns): each hymn can be
converted back to the canonical shape and comes out unchanged.
[FORMAT.md](FORMAT.md) describes what the Markdown looks like and why.

## What is published from it

**<https://ickc.github.io/selected-hymns-and-songs/>** — the site, rebuilt from
`data/` on every push to `main`:

- **Open a hymn by its number.** A hymn is called out by number in a meeting,
  so typing the number is the whole of it; the hymn opens in a new tab.
- **Or search for it** from the box in the header, by a line, a title or a
  phrase in either language. The search reaches every slide, so a
  half-remembered line is enough, and it opens the hymn at that stanza.
- **Each hymn as slides to project**, one stanza at a time with the chorus that
  belongs to it, both languages, sized to fill the screen without overflowing
  it. Add `?grid` to a hymn's URL for two aligned columns instead of
  interleaved lines.

More products from the same data may follow.

## Working on it

[DEVELOPER.md](DEVELOPER.md) — the architecture, the tasks, and how it is
built, checked and published.
