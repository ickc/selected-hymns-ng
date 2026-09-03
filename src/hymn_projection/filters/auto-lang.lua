--[[
The same idea as ucharclasses under XeLaTeX, or luaucharclasses under LuaLaTeX:
walk the text, notice where it changes writing system, and act at the boundary.
Three things differ. It is a pandoc Lua filter, so the one answer serves all
four output formats rather than only the TeX ones. It runs once over the source
instead of on every typesetting run, so what it decided is in the repository to
be read and corrected rather than re-derived invisibly on each build. And what
it emits at a boundary is a language -- `lang`, and `dir` where the script is
right to left -- which a font, a hyphenator, a spell checker and a screen reader
can each act on, rather than a font switch, which only the first can. It also
segments by the Script and Script_Extensions properties rather than by Unicode
block as ucharclasses does, so Greek and Coptic are not one class and CJK
punctuation follows the text it punctuates.

Loaded by bin/md_formatter.py, so it rewrites the source rather than each
render. Neither Quarto nor the vanilla Pandoc recipes know about it.

Multilingual sources otherwise have to carry the language by hand:

    [וַיֹּאמֶר אֱלֹהִים]{lang=he dir=rtl}

which is markup about the writing system, not about the text. Every code point
already declares its script in the Unicode Character Database, so this filter
reads it there instead: a document maps scripts to language tags,

    auto-lang:
      Hebrew: he
      Greek: el
      Han: zh-Hant

and `pixi run format` writes each run of a mapped script into the source as
the Span the author would have written, `dir=rtl` included for the
right-to-left ones. What the four recipes then render is ordinary Pandoc
markup, checked in and reviewable in a diff.

Running it again changes nothing: a span that carries a `lang` is skipped
whole, so only text added since the last run is ever tagged.

A script is not a language: Han cannot tell zh-Hant from ja, and no rule can
tell English from French. The mapping is therefore per document and explicit,
and a hand-written span always wins -- this filter never looks inside one.

script-ranges.lua beside this file is the generated table; see
scripts/generate_script_ranges.py.
]]

local directory = PANDOC_SCRIPT_FILE:match("^(.*)[/\\][^/\\]*$") or "."
local unicode = dofile(directory .. "/script-ranges.lua")

local languages = {}  -- script -> language tag
local mapped = {}     -- script -> true, for the scripts this document maps

local function contains(ranges, codepoint)
  local low, high = 1, #ranges
  while low <= high do
    local middle = (low + high) // 2
    local range = ranges[middle]
    if codepoint < range[1] then
      high = middle - 1
    elseif codepoint > range[2] then
      low = middle + 1
    else
      return true
    end
  end
  return false
end

--- The script a code point's own Script property names, or nil for none.
-- One search over every strong range in the database, which is why the table
-- is generated flat and sorted rather than one list per script.
local function own_script(codepoint)
  local low, high = 1, #unicode.strong
  while low <= high do
    local middle = (low + high) // 2
    local range = unicode.strong[middle]
    if codepoint < range[1] then
      high = middle - 1
    elseif codepoint > range[2] then
      low = middle + 1
    else
      return range[3]
    end
  end
  return nil
end

--- Classify one code point.
-- "script"     its own script, whether or not the document maps it
-- "tied"       belonging with the mapped scripts in the set by Script_Extensions
-- "inherited"  Script=Inherited: it takes the script of what precedes it
-- "neutral"    everything else: spaces, digits, ASCII punctuation
-- Answers are memoised: a search over every script for every code point of a
-- long document is a lot of searching for an alphabet's worth of answers.
local memo = {}

local function classify(codepoint)
  local cached = memo[codepoint]
  if cached then return cached[1], cached[2] end

  local kind, value = "neutral", nil
  local own = own_script(codepoint)
  if own and mapped[own] then
    kind, value = "script", own
  else
    -- Script_Extensions is consulted for every code point the document does
    -- not already own outright, not only for the Common and Inherited ones.
    -- The Arabic-Indic digits are Script=Arabic and also written in Thaana, so
    -- in a Dhivehi document a digit between two Thaana words has to continue
    -- the run rather than end it as unmapped Arabic would.
    for script in pairs(mapped) do
      if contains(unicode.ext[script] or {}, codepoint) then
        kind = "tied"
        value = value or {}
        value[script] = true
      end
    end
    -- Otherwise a script of its own, mapped or not, still ends a run.
    if kind == "neutral" and own then kind, value = "script", own end
    -- A combining mark is Script=Inherited: UAX #24 gives it the script of the
    -- character it sits on. A decomposed ά is alpha followed by U+0301,
    -- which no Script_Extensions entry ties to Greek, so without this the
    -- accent would be left outside the span its base letter went into.
    if kind == "neutral" and contains(unicode.inherited, codepoint) then
      kind = "inherited"
    end
  end
  memo[codepoint] = { kind, value }
  return kind, value
end

--- Split a string into maximal runs of one mapped script.
-- Returns a list of `{text=..., script=...}`, `script` absent for the text
-- between runs, which is marked `foreign` when it is another script's own text
-- rather than neutral. Neutral code points join a run only when it continues
-- on the other side of them, which is what keeps a Hebrew phrase whole without
-- swallowing the space that ends it. Script-tied ones join a run they merely
-- touch, which is what keeps 。 and 」 with the Han text they punctuate.
local function split(text)
  local pieces, run, pending = {}, nil, {}

  local function take(count)
    for index = 1, count do run.text = run.text .. pending[index].char end
    for _ = 1, count do table.remove(pending, 1) end
  end

  local function close()
    if not run then return end
    local tied = 0
    while pending[tied + 1] and pending[tied + 1].tied
      and pending[tied + 1].tied[run.script] do
      tied = tied + 1
    end
    take(tied)
    pieces[#pieces + 1] = run
    run = nil
  end

  local function drain()
    for _, item in ipairs(pending) do
      pieces[#pieces + 1] = { text = item.char, tied = item.tied }
    end
    pending = {}
  end

  for _, codepoint in utf8.codes(text) do
    local char = utf8.char(codepoint)
    local kind, value = classify(codepoint)
    if kind == "script" and mapped[value] then
      if run and run.script == value then
        take(#pending)
        run.text = run.text .. char
      else
        close()
        local first = #pending + 1
        while pending[first - 1] and pending[first - 1].tied
          and pending[first - 1].tied[value] do
          first = first - 1
        end
        local carried = ""
        for index = first, #pending do carried = carried .. pending[index].char end
        for _ = first, #pending do table.remove(pending) end
        drain()
        run = { text = carried .. char, script = value }
      end
    elseif kind == "script" then
      -- Another script's own text ends the run rather than joining it, so it
      -- is kept apart from the neutral text that may sit either side of it.
      close()
      drain()
      pieces[#pieces + 1] = { text = char, foreign = true }
    elseif kind == "inherited" then
      -- The mark goes wherever its base went: onto the end of the run when the
      -- base is the last thing the run took, and otherwise onto the pending
      -- entry the base is in, so the two are carried or drained together.
      local last = pending[#pending]
      if last then
        last.char = last.char .. char
      elseif run then
        run.text = run.text .. char
      else
        pending[#pending + 1] = { char = char }
      end
    else
      pending[#pending + 1] = { char = char, tied = value }
    end
  end
  close()
  drain()

  -- Tied text is left as pieces of its own: it may yet belong to a run that
  -- lives in a neighbouring inline, which only group() can see.
  local merged = {}
  for _, piece in ipairs(pieces) do
    local last = merged[#merged]
    if last and not last.script and not piece.script
      and not last.tied and not piece.tied
      and last.foreign == piece.foreign then
      last.text = last.text .. piece.text
    else
      merged[#merged + 1] = piece
    end
  end
  return merged
end

-- A list of pairs rather than a Lua table: pandoc writes the attributes in the
-- order it is given them, and `pairs` over a table is free to hand them over in
-- either order, which would make the formatter's own output unstable.
local function span(script, inlines)
  local attributes = { { "lang", languages[script] } }
  if unicode.rtl[script] then attributes[#attributes + 1] = { "dir", "rtl" } end
  return pandoc.Span(inlines, pandoc.Attr("", {}, attributes))
end

-- Inline containers that carry nothing of their own, so what is inside them
-- decides which run they belong to. Note is deliberately absent: its content
-- is a separate flow, and absorbing it would stop the filter descending into
-- it. Code, maths and raw inlines are absent because their text is not prose.
local transparent = {
  Emph = true, Link = true, Quoted = true, SmallCaps = true, Span = true,
  Strikeout = true, Strong = true, Subscript = true, Superscript = true,
  Underline = true,
}

--- The scripts a whole piece is tied to: what its tied characters have in
-- common. One untied character is enough to leave it tied to nothing, the same
-- rule split() applies to a run of text.
local function narrow(current, value)
  if current == nil then
    local copy = {}
    for script in pairs(value) do copy[script] = true end
    return copy
  end
  for script in pairs(current) do
    if not value[script] then current[script] = nil end
  end
  return current
end

--- Which run an inline list belongs to, from the text inside it.
-- Returns the script when everything script-bearing inside is that one mapped
-- script, nil when there is nothing script-bearing at all, and false when the
-- list has to stay opaque: another script, prose that is not prose, or a
-- language somebody has already written by hand. A second value carries the
-- scripts a list of nothing but tied text is tied to, so that an emphasised or
-- quoted 。 can still join the Han run it touches.
local function list_script(inlines)
  local found, opaque = nil, false
  local ties, untied = nil, false

  local function scan(items)
    for _, item in ipairs(items) do
      if opaque then return end
      local kind = item.t
      if kind == "Str" then
        for _, codepoint in utf8.codes(item.text) do
          local class, value = classify(codepoint)
          if class == "script" and (not mapped[value] or (found and found ~= value)) then
            opaque = true
            return
          elseif class == "script" then
            found = value
          elseif class == "tied" then
            ties = narrow(ties, value)
          elseif class == "neutral" then
            untied = true
          end
          -- An inherited mark goes with its base, so it neither ties the piece
          -- nor unties it.
        end
      elseif kind == "Space" or kind == "SoftBreak" or kind == "LineBreak" then
        -- Neutral, exactly as at the top level.
        untied = true
      elseif transparent[kind] and not (kind == "Span" and item.attributes.lang) then
        scan(item.content)
      else
        opaque = true
        return
      end
    end
  end

  scan(inlines)
  if opaque then return false end
  if found then return found end
  -- Nothing script-bearing in it, so what it has is a tie, if it has one.
  if untied or not ties or not next(ties) then return nil end
  return nil, ties
end

--- Group an inline list, so a run survives what sits inside it.
-- Spaces keep a run going, and so does a container holding nothing but the
-- run's own script -- otherwise the fullwidth colon before an emphasised or
-- quoted Chinese phrase would fall outside the span and lose its font.
-- Anything else ends the run; its own inline list is visited in its own right.
local function group(inlines)
  -- A run with the whole list to itself takes the neutral text around it. The
  -- full stop ending a paragraph of Greek is that paragraph's, and there is
  -- nothing else in it the full stop could belong to. Where a second language
  -- shares the list -- an English sentence quoting Hebrew -- this does not
  -- apply, and the neutral text stays outside the span, which for a
  -- right-to-left run is where the sentence's own punctuation belongs.
  local whole = list_script(inlines)
  if whole then
    return pandoc.Inlines({ span(whole, pandoc.Inlines(inlines)) })
  end

  local out, run, script, pending = pandoc.Inlines({}), {}, nil, {}
  local changed = false

  -- `pending` holds what has been read since the run last took anything, each
  -- entry with the scripts Script_Extensions ties it to. Carrying that here
  -- rather than only inside split() is what lets tied text reach a run on the
  -- far side of an inline boundary: `*神說*` and a following `。` are one Han
  -- run, and so are `。` and a following `*神說*`.
  local function flush()
    for _, item in ipairs(pending) do out:insert(item.inline) end
    pending = {}
  end

  local function close()
    if script then
      local tied = 0
      while pending[tied + 1] and pending[tied + 1].tied
        and pending[tied + 1].tied[script] do
        tied = tied + 1
      end
      for index = 1, tied do run[#run + 1] = pending[index].inline end
      for _ = 1, tied do table.remove(pending, 1) end
      out:insert(span(script, pandoc.Inlines(run)))
      run, script = {}, nil
      changed = true
    end
    flush()
  end

  local function add(inline, piece_script, tied)
    if not piece_script then
      pending[#pending + 1] = { inline = inline, tied = tied }
      return
    end
    if script == piece_script then
      for _, item in ipairs(pending) do run[#run + 1] = item.inline end
      pending = {}
      run[#run + 1] = inline
      return
    end
    -- Another script's run, or the first one: the tied text at the end of what
    -- is pending belongs to it rather than to whatever came before.
    local first = #pending + 1
    while pending[first - 1] and pending[first - 1].tied
      and pending[first - 1].tied[piece_script] do
      first = first - 1
    end
    local carried = {}
    for index = first, #pending do carried[#carried + 1] = pending[index].inline end
    for _ = first, #pending do table.remove(pending) end
    close()
    script = piece_script
    for _, item in ipairs(carried) do run[#run + 1] = item end
    run[#run + 1] = inline
  end

  for _, inline in ipairs(inlines) do
    if inline.t == "Space" or inline.t == "SoftBreak" then
      add(inline, nil)
    elseif inline.t == "Str" then
      for _, piece in ipairs(split(inline.text)) do
        if piece.foreign then
          close()
          out:insert(pandoc.Str(piece.text))
        else
          add(pandoc.Str(piece.text), piece.script, piece.tied)
        end
      end
    elseif transparent[inline.t] and not (inline.t == "Span" and inline.attributes.lang) then
      -- A container of nothing but tied punctuation carries its ties out with
      -- it, so it reaches a run on either side rather than being read as
      -- ordinary neutral text.
      local content, tied = list_script(inline.content)
      if content == false then
        close()
        out:insert(inline)
      else
        add(inline, content, tied)
      end
    else
      close()
      out:insert(inline)
    end
  end
  close()
  return changed and out or nil
end

return {
  -- A filter's own Meta function runs after its Inlines function, so reading
  -- the mapping has to happen in a separate, earlier filter.
  {
    Meta = function(meta)
      for script, tag in pairs(meta["auto-lang"] or {}) do
        if unicode.names[script] then
          languages[script] = pandoc.utils.stringify(tag)
          mapped[script] = true
        else
          io.stderr:write(
            "[WARNING] auto-lang: no Unicode script named " .. script ..
            " in bin/script-ranges.lua\n")
        end
      end
    end,
  },
  {
    traverse = "topdown",
    -- A hand-written language wins: leave the span, and its contents, alone.
    Span = function(element)
      if element.attributes.lang then return element, false end
    end,
    Inlines = function(inlines)
      if next(mapped) then return group(inlines) end
    end,
  },
}
