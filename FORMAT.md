# The Markdown representation of a hymn

`data/N.md` is a bidirectionally lossless projection of one item of the
canonical YAML collection. This is the contract it keeps; how it is generated,
and what else is built from it, is in [DEVELOPER.md](DEVELOPER.md).

## Stanzas

The checked-in Markdown contains no Pandoc bracketed-span syntax. Each stanza
is a level-one heading followed by one paragraph whose physical lines are hard
line breaks. English and Chinese translations are adjacent lines within that
paragraph.

```markdown
# 1

God, our Father, we adore Thee!
阿爸父神，我們拜你，
We, Thy children, bless Thy Name!
稱頌你名永無止！
```

Text scalars in the canonical YAML are Markdown source, not literal text. The
projection therefore preserves inline constructs such as `*emphasis*` and
`^[inline notes]`; the converter's temporary language spans do not escape or
flatten that markup.

The canonical language order is English then Chinese. After `auto-lang.lua`
restores the language of each line, a repeated language or a transition from
Chinese back to English marks the next YAML lyric-line mapping. This also
retains runs of English-only or Chinese-only mappings without placeholders.

## Localized front matter

Localized mappings are flattened by concatenation:

```yaml
category: 讚美和敬拜——聖父（祂的偉大）
note: Repeat the last two lines重複最後兩行
```

A localized meter has a shared notation followed by its language-specific
suffixes:

```yaml
meter: 11.10.11.10. with chorus和
```

The codec expands the shared `11.10.11.10. ` prefix back into both YAML values.
A meter with zero or one detected language remains a YAML scalar.

## How the languages are recovered

When Markdown is read, the codec injects an `auto-lang` map from Unicode script
to the collection's language tags, and `auto-lang.lua` restores temporary
`lang` spans in the Pandoc tree. The Python codec uses those spans to rebuild
the localized YAML mappings. When Markdown is written, `strip-lang.lua` removes
the temporary spans, and the codec removes the injected map before returning
the source.

The Lua filters and their generated Unicode script table are vendored under
`src/hymn_projection/filters`; their exact origin is recorded in the README
there.

## What this cannot do

The inference is checked against the complete source collection by the test
and regeneration workflow. Text which cannot be distinguished by Unicode
script must be corrected in the canonical data or represented explicitly;
script detection cannot recreate information absent from the text.
