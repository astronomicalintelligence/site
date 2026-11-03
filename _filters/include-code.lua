-- Fill a code block from a file next to the page:
--   ```{.markdown include="SKILL.md"}
--   ```
-- so the page always shows exactly the file that people download.
function CodeBlock(el)
  local f = el.attributes["include"]
  if not f then return nil end
  local dir = pandoc.path.directory(quarto.doc.input_file)
  local fh = io.open(pandoc.path.join({ dir, f }), "r")
  if not fh then
    error("include-code: cannot read " .. f .. " next to " .. quarto.doc.input_file)
  end
  el.text = fh:read("a"):gsub("%s+$", "")
  fh:close()
  el.attributes["include"] = nil
  return el
end
