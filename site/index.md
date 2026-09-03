---
title: 詩歌選集 Selected Hymns
lang: en
# The project renders decks; this one page opts out. How it looks is
# `_quarto.yml`'s business, as it is for the decks.
format: html
---

<form class="hymn-goto" id="hymn-goto" autocomplete="off">
  <label for="hymn-number">Hymn 詩歌</label>
  <input id="hymn-number" type="number" inputmode="numeric"
         min="1" max="{{< meta hymns >}}" step="1" placeholder="1"
         aria-describedby="hymn-goto-message" autofocus>
  <button type="submit">Open 開啟</button>
  <span id="hymn-goto-message" class="hymn-goto-message" role="alert" hidden></span>
</form>
