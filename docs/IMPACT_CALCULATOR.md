# Mutabi impact calculator

Open **Impact calculator** in the workspace, or visit `/#impact`. This is an assumption-based scenario model, not measured product impact. It works without AI credentials or accounting data. English and Arabic are supported.

Enter total monthly team tasks, manual minutes per task, assisted minutes (including human review, exceptions and corrections), adoption percentage, fully loaded hourly staff cost, the share of saved capacity that would reduce cash spending, recurring costs, and one-time setup costs. Currency selection only changes the label; enter every amount in that currency.

Inputs stay in page memory across navigation and language changes. Reloading restores the illustrative example. The calculator does not submit these inputs to the server. Download scenario exports the inputs, formulas, results and adoption sensitivity as JSON; Print scenario prints the assumptions alongside the results.

## Interpretation

- Hours freed = total tasks × adoption fraction × (manual minutes − assisted minutes) / 60.
- Capacity value = hours freed × hourly staff cost. This is the value of released employee time, not automatically a cash saving.
- Positive cash benefit = capacity value × cash realization fraction. The default realization is zero. Use a positive fraction only when spending can decrease. If assisted work takes longer, additional labor is charged in full.
- Net monthly cash = cash benefit − recurring costs.
- First-year net cash = 12 × net monthly cash − setup cost.
- First-year cash ROI = (12 × cash benefit − first-year costs) / first-year costs. Undefined when costs are zero.
- Setup payback = setup cost / positive net monthly cash. No payback is shown when net monthly cash is nonpositive.

The sensitivity table changes adoption to 25%, 50%, 75% and 100%, leaving every other assumption fixed. These are scenarios, not probabilities or confidence intervals. Capacity value and cash benefit overlap and must not be added.

The model assumes a full twelve months at constant workload and adoption. It excludes ramp-up, revenue/collection uplift, financing, taxes and time value of money. No claim about measured savings, DSO improvement, customer demand or provider accuracy is inferred from the projections.

The illustrative example uses 1,000 tasks/month, eight manual minutes, three assisted minutes, 60% adoption, SAR 50/hour, SAR 500/month recurring cost, and SAR 2,000 setup. It releases 50 hours valued at SAR 2,500/month. With zero cash realization, monthly net cash is **−SAR 500**; at an explicitly assumed 40% realization it is **SAR 500**, with four-month setup payback. These are arithmetic examples, not Mutabi performance results.

For the impact slides, label outputs **Projected impact under stated assumptions**, show the key inputs, and pair the scenario with the plan to validate task time, adoption and spending changes in a pilot.
