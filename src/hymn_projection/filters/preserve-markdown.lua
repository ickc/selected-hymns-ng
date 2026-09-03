-- Preserve Markdown source inside automatically inferred metadata spans.
--
-- The Python model stores YAML scalars as Markdown source.  Pandoc parses
-- metadata before auto-lang.lua sees it, so stringify would otherwise turn an
-- Emph back into plain text and lose its asterisks.  Collapse each inferred
-- language run to a Str containing Pandoc's canonical Markdown rendering;
-- Python can then recover both its language and its Markdown source.

local format =
  "markdown-smart+yaml_metadata_block+line_blocks-bracketed_spans-raw_attribute"
local options = pandoc.WriterOptions({ wrap_text = "none" })
local fields = { "author", "category", "meter", "note", "ref", "title" }

local function strip_language(inlines)
  return pandoc.Inlines(inlines):walk({
    Span = function(element)
      element.attributes.lang = nil
      element.attributes.dir = nil
      if element.identifier == "" and #element.classes == 0
        and not next(element.attributes) then
        return element.content
      end
      return element
    end,
  })
end

local function markdown(inlines)
  local document = pandoc.Pandoc({ pandoc.Plain(strip_language(inlines)) })
  return pandoc.write(document, format, options):gsub("\n+$", "")
end

local function inferred_language(inline)
  if inline.t == "Span" and inline.attributes.lang then
    return inline.attributes.lang
  end

  local languages = {}
  inline:walk({
    Span = function(element)
      if element.attributes.lang then languages[element.attributes.lang] = true end
    end,
  })
  local language = next(languages)
  if language and not next(languages, language) then return language end
  return false
end

local function collapse(value)
  -- Since Pandoc 3.6, MetaInlines is exposed to Lua filters directly as an
  -- Inlines value; older releases expose the MetaInlines constructor tag.
  local value_type = pandoc.utils.type(value)
  if value_type ~= "Inlines" and value.t ~= "MetaInlines" then return value end

  local output = pandoc.Inlines({})
  local run, language = pandoc.Inlines({}), nil

  local function flush()
    if not language then return end
    output:insert(pandoc.Span(
      pandoc.Inlines({ pandoc.Str(markdown(run)) }),
      pandoc.Attr("", {}, { { "lang", language } })
    ))
    run, language = pandoc.Inlines({}), nil
  end

  for _, inline in ipairs(value) do
    local item_language = inferred_language(inline)
    if item_language then
      if language and language ~= item_language then flush() end
      language = item_language
      if inline.t == "Span" and inline.attributes.lang == item_language then
        for _, child in ipairs(inline.content) do run:insert(child) end
      else
        run:insert(inline)
      end
    elseif language then
      -- Opaque Markdown such as a raw HTML comment has no script of its own;
      -- it belongs to the language run immediately before it.
      run:insert(inline)
    else
      output:insert(inline)
    end
  end
  flush()
  return output
end

return {
  {
    Meta = function(meta)
      for _, field in ipairs(fields) do
        if meta[field] then meta[field] = collapse(meta[field]) end
      end
      return meta
    end,
  },
}
