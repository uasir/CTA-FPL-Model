# Cross-runtime parity report

**Status: PASS**

## Summary

| Metric | Value |
|---|---:|
| status | PASS |
| python_rows | 2 |
| javascript_rows | 2 |
| shared_keys | 2 |
| missing_in_javascript | 0 |
| extra_in_javascript | 0 |
| python_duplicate_keys | 0 |
| javascript_duplicate_keys | 0 |
| python_null_key_rows | 0 |
| javascript_null_key_rows | 0 |
| features_passed | 4 |
| features_total | 4 |

## Feature results

| Feature | Pass | Compared | Within tolerance | Max absolute error |
|---|---:|---:|---:|---:|
| possession_id | True | 2 | 2 | — |
| pressure_count | True | 2 | 2 | — |
| support_distance_m | True | 2 | 2 | 0.0 |
| has_360_frame | True | 2 | 2 | — |

## 360 coverage

```json
{
  "python": {
    "rows_with_360": 1,
    "rows_without_360": 1,
    "coverage": 0.5
  },
  "javascript": {
    "rows_with_360": 1,
    "rows_without_360": 1,
    "coverage": 0.5
  }
}
```
