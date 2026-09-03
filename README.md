# Selected hymns Markdown projection

This repository is a bidirectionally lossless Markdown projection of
[`selected-hymns`](https://github.com/ickc/selected-hymns). The canonical YAML
collection remains `../selected-hymns/data.yml`; each item is rendered here as
`data/N.md` and can be converted back to the canonical YAML shape.

Run the conversions with:

```sh
pixi run yaml-to-md
pixi run md-to-yaml
```

## Markdown representation

The checked-in Markdown contains no Pandoc bracketed-span syntax. Each stanza
is a level-one heading followed by one paragraph whose physical lines are hard
line breaks. English and Chinese translations are adjacent lines within that
paragraph.

Text scalars in the canonical YAML are Markdown source, not literal text.  The
projection therefore preserves inline constructs such as `*emphasis*` and
`^[inline notes]`; the converter's temporary language spans do not escape or
flatten that markup.

```markdown
# 1

God, our Father, we adore Thee!
阿爸父神，我們拜你，
We, Thy children, bless Thy Name!
稱頌你名永無止！
```

The canonical language order is English then Chinese. After `auto-lang.lua`
restores the language of each line, a repeated language or a transition from
Chinese back to English marks the next YAML lyric-line mapping. This also
retains runs of English-only or Chinese-only mappings without placeholders.

Localized front-matter mappings are similarly flattened:

```yaml
category: 讚美和敬拜——聖父（祂的偉大）
note: Repeat the last two lines重複最後兩行
```

When Markdown is read, the codec injects an `auto-lang` map from Unicode script
to the collection's language tags, and `auto-lang.lua` restores temporary
`lang` spans in the Pandoc tree. The Python codec uses those spans to rebuild
the localized YAML mappings. When Markdown is written, `strip-lang.lua`
removes the temporary spans, and the codec removes the injected map before
returning the source.

A localized meter has a shared notation followed by its language-specific
suffixes:

```yaml
meter: 11.10.11.10. with chorus和
```

The codec expands the shared `11.10.11.10. ` prefix back into both YAML values.
A meter with zero or one detected language remains a YAML scalar.

The inference is checked against the complete source collection by the test
and regeneration workflow. Text which cannot be distinguished by Unicode
script must be corrected in the canonical data or represented explicitly;
script detection cannot recreate information absent from the text.

## Slides

`site/slide/N.md` is a second, one-way projection of the same hymn, written for
a presentation renderer rather than for the canonical YAML:

```sh
pixi run md-to-slide    # data/N.md -> site/slide/N.md, and the pages beside it
pixi run build          # and render every deck with Quarto
pixi run serve          # preview on $QUARTO_PORT
pixi run check-slides   # assert no rendered slide overflows
pixi run chorus-report  # list the hymns whose chorus is resolved
pixi run clean          # remove everything the two generate
```

Nothing reads it back, and none of it is checked in: `data/` is the source, and
the projection, the landing page and the chorus report are all rebuilt from it
here and in CI. `data/N.md` remains the only round trip.

### What it resolves

The source records each stanza once. A congregation sings the chorus again
after every stanza, and which chorus that is has to be worked out:

- 502 hymns have none;
- 314 have one `1-chorus`, repeated throughout;
- 15 pair a chorus with each stanza;
- 17 do neither, replacing the chorus partway through — sometimes **in one
  language only**, so the hymn goes on singing the English of `1-chorus` under
  a new Chinese one.

One rule covers all four: each language takes the most recent chorus at or
before its stanza. Hymn 705 states that instruction in prose
(`第三至第六節用第二節和詩`), and the rule reproduces it without reading the
note. No hymn in the collection places a chorus before its first stanza, so the
resolution never comes up empty.

Which hymns those 17 are is not a judgement about how the choruses are
*written*: hymns 284 and 671 pair a chorus with every stanza and so look
settled, but their later choruses are Chinese only, so English still falls back
to `1-chorus`. `pixi run chorus-report` classifies by what the resolution did,
prints every stanza of every such hymn with the chorus each language takes, and
marks the stanzas where the two differ. `site/chorus.html` is the same list as a
page. CI runs it with `--expect 17`, so a new one cannot arrive unnoticed.

A stanza of more than four lyric lines is divided into the fewest even parts
which fit — an eight-line stanza of a doubled meter halves at its natural
break. `--lines-per-slide` changes the limit.

### What it looks like

A slide holds the stanza label, a `lyrics` Div of one paragraph per lyric line,
and any singing instruction lifted out of the line it was written in:

```markdown
## 1 (1/2) {#v1-1}

::: lyrics
[Christ is risen! Hallelujah!]{lang=en}\
[基督復活！阿利路亞！]{lang=zh-Hant}

[Risen our victorious Head;]{lang=en}\
[得勝的主已復活！]{lang=zh-Hant}
:::
```

The Markdown says what is sung and not how it is laid out. Interleaved is the
default; `?grid` on a deck's URL turns the same file into two aligned columns,
because a paragraph whose box is dissolved leaves its two language spans as
cells of one CSS grid. The projection's `zh` becomes `zh-Hant` here, which is
what a renderer can act on: CSS `:lang()` matches it by prefix, and Pandoc's
LaTeX writer maps it to babel's `chinese-hant`, so the same file also drives a
Beamer build.

The meter is dropped. One hymn of 848 carries a title, so the rest are named by
their opening line, and the number leads the title slide because that is what a
hymn is called out by.

### Fitting, and how it is checked

`site/fit.html` measures every slide against reveal.js's fixed logical viewport
and sets the whole hymn to the smallest type that fits any of its slides — one
size per hymn, so it does not jump between stanzas. Nothing overflows, and
nothing is left small on a screen it could have filled.

It records that size on the document, which is what makes 848 decks checkable
without looking at them: `scripts/check_slides.py` loads each in the headless
browser Quarto installs, fails on a deck that overflows or never fitted, and
reports the decks whose type ended up small enough to want a second look.

## Vendored filters

The Lua filters and their generated Unicode script table are vendored under
`src/hymn_projection/filters`. Their exact origin is recorded in the README in
that directory.
