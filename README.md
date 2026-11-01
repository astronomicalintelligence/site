# Astronomical Intelligence

Source of [astronomicalintelligence.org](https://astronomicalintelligence.org): tested, dated workflows for doing research with language models.

## Run locally

1. Install [Quarto](https://quarto.org/docs/get-started/) (or `pip install quarto-cli`).
2. In this folder run `quarto preview`. The site opens in your browser and reloads on every change.

## Structure

| Folder / file | Content |
|---|---|
| `workflows/` | One `.qmd` file per workflow |
| `prompts/` | One `.qmd` file per prompt |
| `failures/` | One `.qmd` file per documented failure |
| `notes/posts/` | Blog posts |
| `_filters/fits-header.lua` | Builds the FITS-style header from each page's front matter |
| `_templates/workflows.ejs` | Layout of the workflow and prompt lists |
| `styles/` | Fonts, colours (`light.scss`, `dark.scss`) and layout (`base.scss`) |
| `.github/workflows/publish.yml` | Builds the site and publishes it to GitHub Pages on every push to `main` |

To contribute, see [contribute.qmd](contribute.qmd).

## Image credits

`images/hero-xdf.jpg`: Hubble eXtreme Deep Field (HubbleSite release 2012-37). NASA, ESA, G. Illingworth, D. Magee, P. Oesch (UCSC), R. Bouwens (Leiden) and the HUDF09 Team. NASA images are in the public domain; the credit line is kept on the home page.

## Licence

Text: CC BY 4.0. Code: MIT.
