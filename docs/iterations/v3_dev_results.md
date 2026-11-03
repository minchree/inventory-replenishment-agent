**Committed CSVs, all SKUs, 92 simulated days (K = 0)**

| policy | fill rate | stockout days | units short | holding $ | stockout $ | relevant $ | POs |
|---|---|---|---|---|---|---|---|
| P0 starter (s,Q) | 0.810 | 67 | 1043 | 797.22 | 15,308.50 | 16,105.72 | 81 |
| P1 naive agent | 0.982 | 9 | 100 | 3,787.48 | 855.00 | 4,642.48 | 75 |
| P2 EWMA textbook | 0.990 | 4 | 53 | 1,906.32 | 1,325.00 | 3,231.32 | 82 |
| P3 full agent | 0.986 | 9 | 77 | 1,868.14 | 1,959.50 | 3,827.64 | 81 |
| P4 clairvoyant | 1.000 | 0 | 0 | 1,057.28 | 0.00 | 1,057.28 | 77 |
| P3 without defer | 0.990 | 4 | 53 | 2,007.12 | 1,325.00 | 3,332.12 | 81 |
| P3 without reflect | 0.988 | 8 | 67 | 1,802.34 | 1,709.50 | 3,511.84 | 82 |

**200 demand paths, all SKUs: mean (5th-95th percentile)**

| policy | fill rate | stockout days | relevant $ |
|---|---|---|---|
| P0 starter (s,Q) | 0.840 (0.796-0.888) | 55.7 | 14,063 (11,084-17,117) |
| P1 naive agent | 0.978 (0.964-0.991) | 8.4 | 4,567 (3,715-5,633) |
| P2 EWMA textbook | 0.990 (0.980-0.997) | 5.2 | 3,122 (2,254-4,157) |
| P3 full agent | 0.988 (0.976-0.996) | 6.3 | 3,209 (2,297-4,223) |
| P4 clairvoyant | 0.997 (0.992-1.000) | 1.6 | 1,553 (1,086-2,195) |
| P3 without defer | 0.990 (0.980-0.997) | 5.1 | 3,138 (2,248-4,234) |
| P3 without reflect | 0.987 (0.976-0.996) | 6.3 | 3,179 (2,221-4,153) |

**Paired comparison on the same demand paths (relevant cost, all SKUs)**

| comparison | mean difference $ | 5th-95th pct | paths where P3 is cheaper |
|---|---|---|---|
| P3 full agent vs P2 EWMA textbook | +87 | -397 to +734 | 50% |
| P3 full agent vs P3 without defer | +71 | -234 to +730 | 62% |
| P3 full agent vs P3 without reflect | +30 | -463 to +552 | 32% |
| P3 full agent vs P0 starter (s,Q) | -10,854 | -14,153 to -7,805 | 100% |
| P3 full agent vs P1 naive agent | -1,358 | -2,255 to -348 | 98% |

**Safety stock and the cost check, per SKU (full agent, first simulated day)**

| SKU | demand class | alpha | L | SL | z | sigma_1 | SS | S | CSL* | what the costs say | predicted fill | achieved fill |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SKU-A | smooth | 0.1 | 3 | 0.95 | 1.64 | 10.55 | 34.7 | 175.2 | 0.980 | costs favour more protection | 0.994 | 0.999 |
| SKU-B | smooth | 0.1 | 7 | 0.98 | 2.05 | 2.65 | 15.4 | 117.9 | 0.973 | aligned | 0.999 | 0.960 |
| SKU-C | intermittent | 0.1 | 10 | 0.98 | 2.05 | 1.87 | 12.7 | 20.4 | 0.847 | costs favour less protection | 0.998 | 0.951 |
