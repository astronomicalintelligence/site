-- Inserts a FITS-style header with the test metadata at the top of a page.
-- Runs on any page whose front matter has a `qflag` field.

local function s(x)
  if x == nil then return nil end
  return pandoc.utils.stringify(x)
end

local function esc(t)
  return (t:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;"))
end

local qnotes = {
  L0 = "draft, not yet verified",
  L1 = "tested by the author on a real case",
  L2 = "reproduced by a second researcher",
  L3 = "checked across models or dates",
}

-- Author names, whether given as plain strings or as {name, orcid, ...}
local function authors(a)
  if a == nil then return nil end
  if pandoc.utils.type(a) ~= "List" then a = { a } end
  local names = {}
  for _, x in ipairs(a) do
    if type(x) == "table" and x.name then
      local n = x.name
      if type(n) == "table" and n.literal then n = n.literal end
      table.insert(names, s(n))
    else
      table.insert(names, s(x))
    end
  end
  return table.concat(names, ", ")
end

function Pandoc(doc)
  local m = doc.meta
  if not m.qflag then return doc end

  local rows = {
    { "AUTHOR",   authors(m.author),  "who wrote and tested it" },
    { "MODEL",    s(m.model),         "model and version" },
    { "TOOL",     s(m.tool),          "interface or tool" },
    { "TESTED",   s(m.tested),        "date of last test" },
    { "QFLAG",    s(m.qflag),         qnotes[s(m.qflag)] or "verification level" },
    { "TIMESAVE", s(m["time-saved"]), "before -> after" },
    { "PHASE",    s(m.phase),         "research phase" },
  }

  local lines = {}
  for _, r in ipairs(rows) do
    if r[2] and r[2] ~= "" then
      local key = string.format("%-8s=", r[1])
      local val = " '" .. r[2] .. "'"
      local cls = (r[1] == "QFLAG") and "flag" or "v"
      table.insert(lines, string.format(
        '<span class="k">%s</span><span class="%s">%s</span>',
        key, cls, esc(val)))
    end
  end
  table.insert(lines, '<span class="k">END</span>')

  local off = (quarto and quarto.project and quarto.project.offset) or "."
  local html = '<div class="fits-wrap"><div class="fits" role="note" aria-label="Test metadata">'
    .. table.concat(lines, "\n") .. '</div>'
    .. '<a class="fits-help" href="' .. off .. '/start.html#reading-a-workflow">What is this header?</a></div>'
  table.insert(doc.blocks, 1, pandoc.RawBlock("html", html))
  return doc
end
