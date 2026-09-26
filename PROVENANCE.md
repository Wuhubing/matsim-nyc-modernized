# Sources and transformations

- C2SMART Center, New York University: https://doi.org/10.5281/zenodo.7430184. Official archive: C2SMART-Year3-Project.zip, MD5 `47c03996655cda32697952382544958d`. The network, schedule, transit vehicle definitions, mode vehicle definitions and counts match the archive after decompression; see scenarios/nyc-zip-aligned/input-audit.json.
- Population: archived final_population.xml with final_subpopulation.xml merged into person attributes and legacy act tags renamed to activity for MATSim population v6. scripts/merge_subpopulation.py documents this conversion. Original model data are synthetic, not newly collected personal travel records. inputs-sha256.json fingerprints all included compressed simulation inputs.
- Capacity assumptions: paper Tables 3/4, https://arxiv.org/abs/2008.04762, as reconstructed in PublishedNetwork.java. These are explicitly assumed inputs, not the unavailable final external calibration vector.
- 2025 zone: MTA Central Business District Geofence Beginning June 2024, https://catalog.data.gov/dataset/mta-central-business-district-geofence-beginning-june-2024. Mapped to historical road links; excluded highways and grade-separated connections remain approximate.
- Pricing references: https://www.mta.info/document/138931 and https://www.mta.info/document/160966. This repository models selected launch-2025 weekday/E-ZPass provisions, not every subsequent policy change or billing edge case.
- Schema 1 boundary was reconstructed in this workspace because the released toll.xml is a tutorial example, not an NYC cordon.

The supplied upstream project license is retained as LICENSE. Attribution here does not relicense third-party source data or establish endorsements by C2SMART, NYU, MTA or MATSim. Check the cited providers' terms when redistributing modified data.
