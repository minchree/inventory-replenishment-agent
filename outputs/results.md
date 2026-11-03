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
| P0 starter (s,Q) | 0.842 (0.792-0.882) | 54.6 | 14,046 (11,029-17,433) |
| P1 naive agent | 0.978 (0.962-0.990) | 8.6 | 4,512 (3,712-5,415) |
| P2 EWMA textbook | 0.990 (0.980-0.997) | 5.1 | 3,092 (2,208-4,314) |
| P3 full agent | 0.987 (0.977-0.996) | 6.3 | 3,222 (2,175-4,528) |
| P4 clairvoyant | 0.997 (0.991-1.000) | 1.5 | 1,530 (1,091-2,264) |
| P3 without defer | 0.990 (0.980-0.997) | 5.1 | 3,137 (2,195-4,332) |
| P3 without reflect | 0.988 (0.977-0.996) | 6.1 | 3,133 (2,126-4,338) |

**Paired comparison on the same demand paths (relevant cost, all SKUs)**

| comparison | mean difference $ | 5th-95th pct | paths where P3 is cheaper |
|---|---|---|---|
| P3 full agent vs P2 EWMA textbook | +130 | -312 to +870 | 48% |
| P3 full agent vs P3 without defer | +84 | -219 to +647 | 57% |
| P3 full agent vs P3 without reflect | +89 | -428 to +650 | 33% |
| P3 full agent vs P0 starter (s,Q) | -10,825 | -14,365 to -7,866 | 100% |
| P3 full agent vs P1 naive agent | -1,291 | -2,041 to -96 | 96% |

**Safety stock and the cost check, per SKU (full agent, first simulated day)**

| SKU | demand class | alpha | L | SL | z | sigma_1 | SS | S | CSL* | what the costs say | predicted fill | achieved fill |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SKU-A | smooth | 0.1 | 3 | 0.95 | 1.64 | 10.55 | 34.7 | 175.2 | 0.980 | costs favour more protection | 0.994 | 0.999 |
| SKU-B | smooth | 0.1 | 7 | 0.98 | 2.05 | 2.65 | 15.4 | 117.9 | 0.973 | aligned | 0.999 | 0.960 |
| SKU-C | intermittent | 0.1 | 10 | 0.98 | 2.05 | 1.87 | 12.7 | 20.4 | 0.847 | costs favour less protection | 0.998 | 0.951 |
