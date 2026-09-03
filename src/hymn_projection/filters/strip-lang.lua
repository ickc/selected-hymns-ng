--[[
The inverse of auto-lang.lua, for checking it.

Removes `lang` and `dir` from every Span, and removes the Span itself when
those were all it carried. Running it and then auto-lang.lua over the same
sources returns the tagging to what the algorithm derives from the text alone,
so `git diff` afterwards is the whole answer to "what would this produce from
scratch?" -- which is otherwise invisible, because auto-lang.lua leaves an
already tagged span alone and can only ever add to what is there.

`pixi run format-roundtrip` is that pair. It is a debugging tool and not part
of CI: the diff it leaves is meant to be read and then thrown away, and it
cannot tell a hand-written override from a derived span, so the overrides in
src/multilingual.md come back as whatever the document's `auto-lang` map says
instead. That difference is the useful part of the output, not a fault in it.
]]

return {
  {
    Span = function(element)
      element.attributes.lang = nil
      element.attributes.dir = nil
      if element.identifier == "" and #element.classes == 0
        and #element.attributes == 0 then
        return element.content
      end
      return element
    end,
  },
}
