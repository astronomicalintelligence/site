-- Skill pages: after the SKILL.md section, the list of the files in the skill (what Download the skill contains),
-- each linked so it can be read or downloaded alone. Read from the skill's folder at every build, so it is
-- always up to date. The page itself, its images (figure-N), archives and hidden files are not part of the skill.
local function skip(name)
  return name == "index.qmd" or name:match("^figure%-%d+%.") or name:match("%.zip$")
      or name:match("^%.") or name:match("^_")
end

local function walk(dir, prefix, out)
  local ok, names = pcall(pandoc.system.list_directory, dir)
  if not ok then return out end
  table.sort(names)
  for _, name in ipairs(names) do
    if not skip(name) then
      local path = dir .. "/" .. name
      local sub = pcall(pandoc.system.list_directory, path)
      if sub then
        walk(path, prefix .. name .. "/", out)
      else
        table.insert(out, prefix .. name)
      end
    end
  end
  return out
end

function Pandoc(doc)
  local input = (quarto and quarto.doc and quarto.doc.input_file) or ""
  if not input:match("skills/AIS[%dX]+%-[^/]+/index%.qmd$") then return nil end
  local files = walk(pandoc.path.directory(input), "", {})
  if #files <= 1 then return nil end            -- SKILL.md alone: nothing to add
  -- SKILL.md first, then the rest in alphabetical order
  table.sort(files, function(a, b)
    if a == "SKILL.md" then return b ~= "SKILL.md" end
    if b == "SKILL.md" then return false end
    return a < b
  end)
  local items = {}
  for _, f in ipairs(files) do
    table.insert(items, { pandoc.Plain({ pandoc.Link({ pandoc.Code(f) }, f) }) })
  end
  local blocks = { pandoc.Para({ pandoc.Str("Files"), pandoc.Space(), pandoc.Str("in"), pandoc.Space(),
                                 pandoc.Str("the"), pandoc.Space(), pandoc.Str("skill:") }),
                   pandoc.BulletList(items) }
  -- at the end of the SKILL.md section: before the next level-2 heading after it
  local in_section = false
  for i, b in ipairs(doc.blocks) do
    local actions = b.t == "RawBlock" and b.text:match('class="page%-actions"')   -- the "Used it?" box
    if (b.t == "Header" and b.level == 2) or actions then
      if in_section then
        for k = #blocks, 1, -1 do doc.blocks:insert(i, blocks[k]) end
        return doc
      end
      in_section = b.t == "Header" and pandoc.utils.stringify(b) == "SKILL.md"
    end
  end
  return nil
end
