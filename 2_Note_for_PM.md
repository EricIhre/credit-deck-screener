# Can we flag which of these issuers do well or badly afterwards, and should you trust it?
Yes, within limits. We can pull financial data out of the reports and build a simple model that ranks the issuers by risk, flagging which are *likely to do best* and *likely to do worst* over the weeks after their presentation. We trained it on the 2024 reports and then validated it on the 2025 reports, 25 each. It held up on issuers it had never seen, though on only 25 of them, so treat it as a watchlist rather than a trade trigger. The dataset is still quite small, which is the main thing to be cautious about, so use it to flag which issuers are worth a closer look, not as a verdict to trade on. In the future, a larger dataset could give a stronger signal and allow a more sophisticated model, which is worth investigating.

## How the model works
For each issuer we pull a lot of information from the presentations, but because of the data constraint we use two to assess the risk:

1. **Net leverage**, and
2. **EBITDA change from the last year** (improving or deteriorating vs a year earlier).

These two variables are equally weighted and combined into a single risk score, so higher net leverage and a large negative change result in a high risk score. The risk score should not be used on its own but to rank the issuers and divide them into three buckets: low, medium and high risk. The risk score is defined as:

```
risk_score =  (net_leverage - mean(net_leverage)) / sd(net_leverage)
            - (EBITDA_change - mean(EBITDA_change)) / sd(EBITDA_change)
```

In words: we standardise each metric, then subtract, so a issuer is riskier the more its leverage is above average and its EBITDA trend below.

## Can we trust the data and the model?
The risk score is built on the reports from 2024 (variable selection, for example) and then validated on the reports from 2025. The metric used to evaluate a ranking model is Spearman correlation, and for the out-of-time sample we got a rho = -0.753 with p-value < 0.001. Because this is a risk score, a strong negative correlation is what we want: higher risk lines up with lower returns. This should still be taken with some caution, as the dataset is quite small, but it is an encouraging result.

As the data comes from PDFs, it is validated by checking numerical ranges for each of the financials, as well as recalculating the financials that are derived from others. A sample of the data is also validated by an independent LLM. 

## How you'd use it
My recommendation is to use the model as a guiding tool, that is, to flag which issuers to look into. I would not use it as a deciding factor to trade on without established and proven model inputs.

## Next steps
Because we got good results from this initial analysis with 50 data points, continuing the work with a larger dataset could give better confidence and a stronger signal.