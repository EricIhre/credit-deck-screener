# Data Extraction
## Extraction
For the extraction, I used the Python package pdfplumber to get the raw text and then regular expression matching to get the different features. There were some challenges with this method that I had to take into account.
- Mixed currency units. In the financial tables there were different currency units: some were EUR '000s and others EUR millions.
- Margin trend was also disclosed in two ways. Some documents had the prior-year margin explicitly, and others had a signed delta.
- Leverage was sometimes omitted, but net debt and EBITDA were always given, so if it was missing, I derived it as net_debt/EBITDA.

## Validation
I used two methods to validate the data extraction.

### Numerical validation
First, I checked the ranges of every numerical field and the allowed values for each categorical field. So, for example, I checked that all values in founded_year were between 1800 and 2025. I also checked that the features that could be calculated from other features gave the same result, for example, that leverage was equal to the stated net_debt/EBITDA (within 10%). 

### LLM sample validation
For the second check, I used an LLM to extract the data from 4 PDFs that I hand-picked to be different and to create a JSON file with the same features as the regular expression matching extraction. Then I cross-checked the regular expression matching extraction against the LLM's extraction.

## Scaling
To scale this and make it more robust, I would use an LLM instead of my regular expression matching, but keep the output constraint (output in a pre-selected JSON schema) and keep the numerical validation as well as the LLM sampling validation.
