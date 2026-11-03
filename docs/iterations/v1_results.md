**Committed CSVs, all SKUs, 92 simulated days (K = 0)**

| policy | fill rate | stockout days | units short | holding $ | stockout $ | relevant $ | POs |
|---|---|---|---|---|---|---|---|
| P0 starter (s,Q) | 0.810 | 67 | 1043 | 797.22 | 15,308.50 | 16,105.72 | 81 |
| P1 naive agent | 0.982 | 9 | 100 | 3,787.48 | 855.00 | 4,642.48 | 75 |
| P2 EWMA textbook | 0.990 | 4 | 53 | 1,906.32 | 1,325.00 | 3,231.32 | 82 |
| P3 full agent | 0.980 | 10 | 111 | 2,576.58 | 1,412.00 | 3,988.58 | 79 |
| P4 clairvoyant | 1.000 | 0 | 0 | 1,057.28 | 0.00 | 1,057.28 | 77 |
| P3 without defer | 0.984 | 8 | 87 | 2,641.40 | 1,376.00 | 4,017.40 | 80 |
| P3 without reflect | 0.988 | 8 | 67 | 1,802.34 | 1,709.50 | 3,511.84 | 82 |

**200 demand paths, all SKUs: mean (5th-95th percentile)**

| policy | fill rate | stockout days | relevant $ |
|---|---|---|---|
| P0 starter (s,Q) | 0.840 (0.796-0.888) | 55.7 | 14,063 (11,084-17,117) |
| P1 naive agent | 0.978 (0.964-0.991) | 8.4 | 4,567 (3,715-5,633) |
| P2 EWMA textbook | 0.990 (0.980-0.997) | 5.2 | 3,122 (2,254-4,157) |
| P3 full agent | 0.982 (0.966-0.993) | 8.1 | 3,640 (2,657-4,830) |
| P4 clairvoyant | 0.997 (0.992-1.000) | 1.6 | 1,553 (1,086-2,195) |
| P3 without defer | 0.985 (0.972-0.995) | 6.8 | 3,563 (2,706-4,573) |
| P3 without reflect | 0.987 (0.976-0.996) | 6.3 | 3,179 (2,221-4,153) |

**Paired comparison on the same demand paths (relevant cost, all SKUs)**

| comparison | mean difference $ | 5th-95th pct | paths where P3 is cheaper |
|---|---|---|---|
| P3 full agent vs P2 EWMA textbook | +518 | -179 to +1,379 | 9% |
| P3 full agent vs P3 without defer | +77 | -293 to +824 | 62% |
| P3 full agent vs P3 without reflect | +461 | -214 to +1,243 | 12% |
| P3 full agent vs P0 starter (s,Q) | -10,423 | -13,693 to -7,223 | 100% |
| P3 full agent vs P1 naive agent | -927 | -1,767 to +124 | 92% |

**Safety stock and the cost check, per SKU (full agent, first simulated day)**

| SKU | demand class | alpha | L | SL | z | sigma_1 | SS | S | CSL* | what the costs say | predicted fill | achieved fill |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SKU-A | smooth | 0.1 | 3 | 0.95 | 1.64 | 10.55 | 34.7 | 175.2 | 0.979 | costs favour more protection | 0.994 | 0.984 |
| SKU-B | smooth | 0.1 | 7 | 0.98 | 2.05 | 2.65 | 15.4 | 117.9 | 0.973 | aligned | 0.999 | 0.969 |
| SKU-C | intermittent | 0.1 | 10 | 0.98 | 2.05 | 1.87 | 12.7 | 20.4 | 0.847 | costs favour less protection | 0.998 | 1.000 |
