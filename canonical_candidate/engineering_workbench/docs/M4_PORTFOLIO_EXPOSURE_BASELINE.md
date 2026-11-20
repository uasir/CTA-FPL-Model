# M4-T5 — Non-covariance portfolio exposure baseline

`scripts/m4_portfolio_exposure_baseline.py` summarizes field exposure for the
frozen HOLD squad and, when supplied, the frozen candidate transfer scenario.
It keeps squad, starting XI and outfield bench sums separate for ownership,
standard EO, starting, captain, Triple Captain and scoring exposure.

It also reports top-player field EO, top-3/top-5 concentration shares, HHI and
effective contributor count for the squad and starting XI, plus captain-share
differential. These are marginal exposure/template concentration descriptions,
not player correlations, covariance, points variance, rank forecasts or utility.

A portfolio sum is withheld if any included player value is null. Concentration
is withheld if any player value is missing or the total exposure is zero. No
missing value is converted to zero. CoVar remains disabled and the output is
not release eligible.
