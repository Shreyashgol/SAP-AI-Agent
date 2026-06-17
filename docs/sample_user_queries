Five complex, runtime-answerable queries

  All grounded in columns that actually exist in your data (OCRD, OITM, OINV, INV1, ORDR, OWHS):

  1. Top customers — revenue vs. exposure

  ▎ "Show my top customers by total invoiced amount, alongside their current outstanding balance."

  - Exercises: SUM(OINV.DocTotal) grouped by CardCode, joined to OCRD (CardName, Balance), ranked. Maps to Revenue + Customer 
  Balance / top_customers.

  2. Inventory value by category

  ▎ "What's the total value of stock on hand, broken down by item category?"

  - Exercises: SUM(OITM.OnHand * OITM.AvgPrice) GROUP BY Category. Maps to Inventory Value / inventory_status.

  3. Open orders not yet invoiced (anti-join)

  ▎ "Which customers have sales orders that haven't been turned into invoices yet?"

  - Exercises: ORDR LEFT JOIN OINV on CardCode/DocEntry, filtering where no matching invoice exists. Tests set-difference
  reasoning.

  4. Monthly revenue trend + average ticket

  ▎ "Give me total invoiced revenue per month for 2025, and the average invoice value."

  - Exercises: time-bucketing on OINV.DocDate, SUM + AVG(DocTotal). Maps to Revenue / sales_summary.

  5. Invoice ↔ line-item reconciliation (data quality)

  ▎ "For each invoice, compare the header total to the sum of its line totals, and flag any that don't match."

  - Exercises: OINV JOIN INV1 on DocEntry, SUM(INV1.LineTotal) vs OINV.DocTotal. With only 2 INV1 rows against 5 invoices, this
  will surface real mismatches — a good stress test of joins + aggregation + comparison.