---
name: radio-fits-units
description: Use when reading or measuring radio FITS images or cubes
  (WSClean, CASA, DDFacet, AIPS headers), integrated fluxes, beams,
  or Jy/beam conversions.
---

# Radio FITS images and flux units

1. Open with astropy.io.fits; build the WCS with `.celestial` so that
   FREQ and STOKES axes are dropped. Squeeze the data to 2D.
2. Beam: read BMAJ, BMIN (degrees) and BPA. If absent, look for a
   beam table. If still absent, stop and ask; never assume a beam.
3. Beam area in pixels:
   area = pi * BMAJ * BMIN / (4 ln 2) / |CDELT1 * CDELT2|
4. Integrated flux [Jy] = sum(pixels in region) [Jy/beam] / area.
5. Keep every quantity as an astropy Quantity and print units.
6. Report the error: rms * sqrt(N_pix / area), plus a calibration
   term the user states (ask if unknown).
