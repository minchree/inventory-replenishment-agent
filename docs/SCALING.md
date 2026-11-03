# Scaling note

**Deployment.** Package the `replenish` module in a container and run it once a day as a scheduled job, for example Cloud Scheduler triggering a Cloud Run job or a scheduled ECS task, after the nightly sales export lands. SKUs are independent, so large catalogs shard by SKU across parallel tasks. For the first months the job writes recommended POs for a buyer to approve, not orders straight to the ERP.

**Monitoring.** Ship the daily log and `decisions.csv` to central logging. Alert when a SKU's rolling 7-day fill rate falls more than 2 points below its target, when the tracking signal raises an ALERT (already in the log), and when forecast MAE drifts above its 28-day baseline. A daily dashboard shows stockouts, fill rate and cost per SKU.

**Reliability.** Key each run by date and SKU so a retried job can't place a PO twice. Retry ERP and data-feed calls with exponential backoff. Validate inputs before deciding: `SkuParams` already rejects impossible lead times, MOQs and service levels. A missing day in the sales feed must stop the decision for that SKU and raise an alert. Today the code reads a missing day as zero demand, which is right for the order-line CSV but wrong for a feed outage.

**Cost controls.** The 30-days-of-cover cap on any single PO is already in `plan_order`. `avg_inventory_value` tracks the working capital tied up in stock. In production, add a budget ceiling per category that blocks new POs when stock value would exceed it, and send those blocks to a buyer.
