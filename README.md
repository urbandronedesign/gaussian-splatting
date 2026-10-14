# Gaussian Splatting · Récits urbains

A bilingual (FR/EN) course manual for a one-day introduction to Gaussian splatting for design students:
theory in the morning, fieldwork on the Île de Nantes (Quartier de la Création) in the afternoon.

- **Manual:** [`splatting_manuel-v1.html`](splatting_manuel-v1.html), a single self-contained file that works offline.
- **Companion page:** [`outils.html`](outils.html), with tools, versions, formats and hardware. It is dated and updated separately.

| Part | Chapters |
|---|---|
| Preamble | How to use the manual, what to hand in, the day |
| I · Understanding | 1 A new medium · 2 What a splat is · 3 How a splat is made · 4 Splats among other 3D |
| II · Telling | 5 Urban narratives |
| III · Tools | 6 Scaniverse · 7 LichtFeld Studio · 8 SuperSplat |
| IV · Fieldwork | 9 Île de Nantes (map, brief, hand-in) · 10 Symptoms and fixes |
| Reference | FAQ · Glossary FR/EN |

There are 12 inline SVG diagrams and an OpenStreetMap-based map, all bilingual and theme-aware.

## Maintaining

```bash
python tools/audit.py        # 7 passes; exit code = number of failing passes
```

- Edit the manual with scripts (`assert t.count(old) == 1`), writing FR and EN together.
- Screenshots still to take are listed in [`CAPTURE-GUIDE.md`](CAPTURE-GUIDE.md). Open `splatting_manuel-v1.html?figures` to see the empty slots.
- Perishable facts (versions, prices, formats) belong in `outils.html`, not in the manual body.

## Credits

The method is from Kerbl, Kopanas, Leimkühler and Drettakis, *3D Gaussian Splatting for Real-Time Radiance Field Rendering*, SIGGRAPH 2023.
The tools are Scaniverse (Niantic Spatial), LichtFeld Studio (MrNeRF and contributors, GPL-3.0) and SuperSplat (PlayCanvas, MIT).
Map data © OpenStreetMap contributors, ODbL.
The format follows the coursebook skill.
