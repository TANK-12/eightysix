# Juggernaut mass with 20 mm Dyneema rope on the spools

date: 2026-10-02 · for: both

- Rope: 20 mm Dyneema, 0.22 kg/m. Each wire spool now carries 17.6 kg of rope on top of its 30 kg frame (47.6 kg).
- Mass table, combat loaded: 5423 -> 5354 kg. The Juggernaut in the game (table plus 140.4 kg of MG belts): 5563.7 -> 5493.9 kg (-69.8 kg: the old spool estimate was heavier).
- Source: `~/Models/juggernaut/model2/realistic_mass/realistic_mass.py` (backups `*.before-dyneema-2026-10-02`),
  then `tools/build_juggernaut_data.py` regenerated `data/parts.json` and `data/mechs.json` in ~/Games/eightysix.
- Only spools, wiring and centre of mass changed in the data diff. `tests/test_juggernaut.gd` 27/27 with the new figures.
- Reasoned estimate, not a measured one (rope length per spool comes from the model).
