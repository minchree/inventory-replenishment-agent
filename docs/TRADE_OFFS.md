# Inventory vs service: the trade-offs

More safety stock buys fewer stockouts with more holding cost, and where the balance sits depends on what a stockout costs compared with a day of holding. The service-level sweep (`outputs/sl_sweep.csv`, 100 held-out demand paths) shows all three cases.

SKU-A is cheap to hold and its stockout cost is comparatively high, so raising its service level from the configured 0.95 to 0.98 lowers mean cost from $135.64 to $133.93. The configured target is too low for its own economics, and CSL* (0.98) says so.

SKU-C is the opposite. An $80 unit with a 24-unit minimum order sits on the shelf for about two weeks. Holding it at a 0.98 service level costs $1,037 per path, against $936 at 0.80, and the extra spend buys 1.8 points of fill rate. That can still be the right call if missing an order for this item costs more than the $40 stockout parameter captures, for example by losing a customer. That is a business decision, and the agent leaves it with the buyer.

SKU-B has promo days that a normal model doesn't expect, so even at 0.98 its fill rate is about 0.97. Cost keeps falling all the way to 0.995. The defer rule shows the same tension day to day: on SKU-C, waiting saves holding cost and rarely hurts, while on SKU-B a one-day wait, made while the forecast was running behind the rising trend, produced a 4-unit stockout that cost about eight times the holding it saved.

The cheapest policy isn't automatically the right one. A stockout on a promoted item damages trust in a way a per-unit penalty doesn't measure. That's why the agent reports where cost and service disagree instead of quietly optimizing one of them.
