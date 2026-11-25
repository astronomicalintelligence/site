-- Puts the kind of contribution (Workflow, Prompt, Skill, ...) first among the tags under the title
-- of every contribution page (<type>/AI<letter><number>-<name>/index.qmd), also when it has no other tags.
-- The kind comes from the section folder (skills/, prompts/, ...).
local NAMES = { workflows = "Workflow", prompts = "Prompt", skills = "Skill", ["agent-configs"] = "Agent config",
                guides = "Guide", ["model-checks"] = "Model check", reviews = "Review", failures = "Failure" }

function Meta(m)
  local input = (quarto and quarto.doc and quarto.doc.input_file) or ""
  -- <type>/AI<letter><number>-<name>/index.qmd; section list pages are left alone
  local kind = input:match("([%w-]+)/AI%u[%dX]+%-[^/]+/index%.qmd$")
  if not NAMES[kind] then return nil end
  local cats = pandoc.List({ pandoc.MetaInlines(pandoc.Inlines(NAMES[kind])) })
  if m.categories then
    for _, c in ipairs(m.categories) do cats:insert(c) end
  end
  m.categories = cats
  -- Quarto turns every tag into a link to a list filtered by that tag; "Prompt" is not a real tag, so its
  -- link goes to the Library showing that kind (or to the list of guides) instead of an empty list
  local target = kind == "guides" and "../index.html" or ("../../library.html#type=" .. kind)
  quarto.doc.include_text("after-body", ([[
<script>
(function () {
  function fix() {
    var a = document.querySelector("header.quarto-title-block .quarto-category:first-child a");
    if (a) a.setAttribute("href", "TARGET");
  }
  document.addEventListener("DOMContentLoaded", function () { setTimeout(fix, 0); });
  window.addEventListener("load", fix);
})();
</script>]]):gsub("TARGET", target))
  return m
end
