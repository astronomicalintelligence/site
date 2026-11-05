-- Adds, before the History of every published contribution page, links that open a GitHub issue form with the
-- contribution already filled in: "Suggest an update" (form 8) and, except on failures, "It failed for me" (form 7).
-- GitHub fills a form field from the URL parameter named after the field's id (catalog, what) and the title.
local NEW_ISSUE = "https://github.com/astronomicalintelligence/site/issues/new"

local function enc(s)
  return (s:gsub("[^%w%-%._~]", function(c) return string.format("%%%02X", string.byte(c)) end))
end

local function url(params)
  local parts = {}
  for _, kv in ipairs(params) do table.insert(parts, kv[1] .. "=" .. enc(kv[2])) end
  return NEW_ISSUE .. "?" .. table.concat(parts, "&")
end

function Pandoc(doc)
  local input = (quarto and quarto.doc and quarto.doc.input_file) or ""
  local kind = input:match("([%w-]+)/AI%u%d+%-[^/]+/index%.qmd$")      -- published contributions only (no XXXX)
  if not kind or not doc.meta.catalog then return nil end
  local cat = pandoc.utils.stringify(doc.meta.catalog)
  local title = doc.meta.title and pandoc.utils.stringify(doc.meta.title) or ""

  local links = {
    string.format('<a class="page-action" href="%s">Suggest an update</a>',
      url({ { "template", "8-update.yml" }, { "title", "[Update] " .. cat .. " " }, { "catalog", cat } })),
  }
  if kind ~= "failures" then
    table.insert(links, string.format('<a class="page-action" href="%s">It failed for me</a>',
      url({ { "template", "7-failure.yml" }, { "title", "[Failure] " },
            { "what", "While using " .. cat .. " (" .. title .. "): " } })))
  end
  local box = pandoc.RawBlock("html", '<div class="page-actions"><span class="page-actions-label">Used it?</span>'
    .. table.concat(links, "") .. "</div>")

  -- before the History section, or at the end
  for i, b in ipairs(doc.blocks) do
    if b.t == "Header" and b.level == 2 and pandoc.utils.stringify(b) == "History" then
      doc.blocks:insert(i, box)
      return doc
    end
  end
  doc.blocks:insert(box)
  return doc
end
