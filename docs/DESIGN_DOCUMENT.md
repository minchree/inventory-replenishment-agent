# Design document

## Goal

The agent keeps three SKUs in stock at the lowest total cost. Each day it decides, per SKU, whether to place a purchase order and how big, aiming to meet each SKU's service level while minimizing holding, stockout and ordering costs.

## Inputs and outputs

Inputs, read fresh at every daily review:
- daily demand history (`sales.csv`, aggregated per SKU per day)
- on-hand stock, open POs and backorders, starting from `inventory.csv`
- per-SKU parameters from `params.csv`: lead time, minimum order quantity, service level, unit, holding and stockout costs
- the agent's own EWMA forecast and its recent forecast errors

Outputs, per SKU per day: one action (ORDER with a quantity, HOLD, or DEFER) and a log line giving the numbers behind it. An ALERT line appears when the agent adjusts its own forecast.

## Guardrails

- Every PO is at least `min_order_qty`.
- Lead time is respected. Decisions use inventory position (on hand + on order − backorders) over L + 1 days, so stock already in transit is never ordered twice.
- Safety stock comes from `service_level` and the agent's measured forecast error.
- No single order exceeds 30 days of forecast demand unless the minimum order quantity requires it. This stops a bad data point or a broken forecast from triggering a huge PO.
- Waiting is allowed only when its expected stockout cost is below the holding cost it saves, and only if the service level it accepts stays within 2 points of the target. This is where holding cost is traded against stockout cost, one decision at a time.

## Metrics

- Stockouts: days with any unit short, and the number of units short.
- Fill rate: units served from stock on the day they were demanded, divided by units demanded.
- Total cost: holding (per unit per day on end-of-day stock) + stockout (once per unit short) + ordering (per PO; 0 here, 25 in a second run). Purchase spend is reported separately.

## Ethics and trust

A stockout breaks a promise to a customer, and excess stock ties up money that someone else has to answer for. The agent balances service reliability against cost control explicitly and shows its work. Every action is logged with the forecast, safety stock, inventory position and the cost comparison behind it, so a buyer can audit any PO, disagree with it, and see exactly which number to change. When the configured service level and the cost parameters disagree, the agent reports it (CSL*) rather than overriding a target a person set. Its tracking signal flags when its own forecast has gone wrong, so problems surface in the log instead of in empty shelves.
