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
is a level-one heading followed by one Pandoc line block. English and Chinese
translations are adjacent lines within that block.

Text scalars in the canonical YAML are Markdown source, not literal text.  The
projection therefore preserves inline constructs such as `*emphasis*` and
`^[inline notes]`; the converter's temporary language spans do not escape or
flatten that markup.

```markdown
# 1

| God, our Father, we adore Thee!
| 阿爸父神，我們拜你，
| We, Thy children, bless Thy Name!
| 稱頌你名永無止！
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

The projection includes an `auto-lang` map from Unicode script to the
collection's language tags. When Markdown is read, `auto-lang.lua` restores
temporary `lang` spans in the Pandoc tree; the Python codec uses those spans to
rebuild the localized YAML mappings. When Markdown is written, `strip-lang.lua`
removes the codec's temporary spans before Pandoc emits the source.

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

## Vendored filters

The Lua filters and their generated Unicode script table are vendored under
`src/hymn_projection/filters`. Their exact origin is recorded in the README in
that directory.
