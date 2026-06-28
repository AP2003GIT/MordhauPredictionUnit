# Mordhau Prediction Unit Mathematics

This document describes the current math used by the prediction service. The system has two layers:

1. An explainable baseline rating and probability model.
2. A trained logistic regression model that learns from completed historical matches.

The baseline remains useful even when no trained ML model exists.

## Symbols

```text
R_p       raw rating for player p
D_p       displayed rating for player p
K         Elo update strength, currently 32
n         number of players on a team
A_t       actual result for team t: 1 for win, 0 for loss
E_t       expected result for team t
P_t       predicted win probability for team t
```

Team IDs:

```text
team 0 = Iron Company
team 1 = Free Guard
```

## Raw Player Rating

Every new player starts with:

```text
R_p = 1000
```

For each completed historical match, the system computes each team's average raw rating:

```text
team_rating_t = average(R_p for players p on team t)
```

Then it computes the expected win chance using the Elo formula:

```text
E_0 = 1 / (1 + 10 ^ ((team_rating_1 - team_rating_0) / 400))
E_1 = 1 - E_0
```

After the match result is known, every player on each team is updated:

```text
R_p_new = R_p_old + K * (1 / sqrt(n)) * (A_t - E_t)
```

Because `K = 32`, a 5v5 team update is scaled by:

```text
32 * (1 / sqrt(5)) = 14.31
```

Example:

```text
expected win chance = 0.40
actual result       = 1
team size           = 5

rating change = 32 * (1 / sqrt(5)) * (1 - 0.40)
rating change = 8.59
```

So each player on that winning team gains about `+8.6` raw rating.

If a team was expected to win and loses, the same formula gives a negative rating change.

## Player Combat Stats

The rating system also tracks cumulative combat stats:

```text
matches += 1
wins    += 1 if player's team won
kills   += match kills
deaths  += match deaths
assists += match assists
damage  += match damage
adr     += match ADR
```

From those totals:

```text
win_rate = wins / matches
kd       = kills / max(1, deaths)
kda      = (kills + 0.35 * assists) / max(1, deaths)
avg_adr  = adr_total / matches
```

Assists count as `0.35` of a kill inside KDA. That keeps assists meaningful without making them equal to kills.

## Display Rating

The dashboard does not show raw Elo directly. It shows:

```text
D_p = R_p + experience_bonus + impact_bonus
```

Experience bonus:

```text
experience_bonus = min(60, ln(1 + matches) * 12)
```

Impact bonus:

```text
impact_bonus = min(90, max(-60, (kda - 1.0) * 34))
```

This means:

- More completed matches slowly raise displayed rating.
- The experience bonus is capped at `+60`.
- KDA above `1.0` raises displayed rating.
- KDA below `1.0` lowers displayed rating.
- The impact bonus is capped between `-60` and `+90`.

Example:

```text
raw rating = 1050
matches    = 100
kda        = 1.50

experience_bonus = min(60, ln(101) * 12)
experience_bonus = 55.38

impact_bonus = min(90, max(-60, (1.50 - 1.0) * 34))
impact_bonus = 17.00

display rating = 1050 + 55.38 + 17.00
display rating = 1122.38
```

## Aggregate Player Fallback

Some known players may have leaderboard aggregate stats but no stored match-by-match history. Those players get a fallback displayed rating:

```text
kda = (kills + 0.35 * assists) / max(1, deaths)

experience_bonus = min(50, ln(1 + matches) * 8)
impact_bonus     = min(80, max(-70, (kda - 1.0) * 30))

display_rating = 1000 + experience_bonus + impact_bonus
```

This fallback is more conservative than match-history ratings because it does not know who the player beat or lost to.

## Team Rating

For a prediction, each team's strength is usually the average displayed rating:

```text
team_display_rating_t = average(D_p for players p on team t)
```

The random 5v5 generator uses this directly:

```text
rating_diff = team_display_rating_0 - team_display_rating_1
P_0 = sigmoid(rating_diff / 180)
P_1 = 1 - P_0
```

Where:

```text
sigmoid(x) = 1 / (1 + exp(-x))
```

So if team 0 is stronger by `180` displayed rating points:

```text
P_0 = sigmoid(180 / 180)
P_0 = sigmoid(1)
P_0 = 0.731
```

That means about a `73%` predicted chance for team 0.

## Live Match Probability

For a live match, the model uses more than rating. It also uses current scoreboard impact and score difference.

Per-player live impact:

```text
live_impact_p =
    kills   * 16
  + assists * 5
  + damage  * 0.035
  + adr     * 0.3
  - deaths  * 11
```

Team live impact:

```text
team_live_impact_t = average(live_impact_p for players p on team t) + current_score_t * 12
```

Differences:

```text
rating_diff = team_display_rating_0 - team_display_rating_1
live_diff   = team_live_impact_0 - team_live_impact_1
score_diff  = current_score_0 - current_score_1
```

Final live-match logit:

```text
logit = (rating_diff / 180) + (live_diff / 120) + (score_diff * 0.65)
```

Win probabilities:

```text
P_0 = sigmoid(logit)
P_1 = 1 - P_0
```

This means:

- A `+180` rating gap contributes about `+1.0` logit.
- A `+120` live-impact gap contributes about `+1.0` logit.
- A `+1` score lead contributes `+0.65` logit.

## Confidence

Confidence is based on the smaller team's amount of historical data:

```text
sample_size = min(
    total historical matches for team 0 players,
    total historical matches for team 1 players
)
```

Then:

```text
confidence = min(0.95, 0.25 + ln(1 + sample_size) / 9)
```

This keeps confidence low when one side has little history, even if the rating gap is large.

Example:

```text
sample_size = 100
confidence = min(0.95, 0.25 + ln(101) / 9)
confidence = 0.763
```

So confidence is about `76%`.

## Machine Learning Model

The ML model trains on historical completed matches.

Each training row is:

```text
features before match -> winner
```

The important part is avoiding leakage. For each match:

1. Build team features using only ratings and stats known before that match.
2. Record the winner as the label.
3. Update player ratings after the match.

The label is:

```text
y = 1 if team 0 won
y = 0 if team 1 won
```

## ML Features

The ML model learns from team-difference features:

```text
avg_rating_diff      = team0 avg rating      - team1 avg rating
top_rating_diff      = team0 top rating      - team1 top rating
weakest_rating_diff  = team0 weakest rating  - team1 weakest rating
rating_spread_diff   = team0 rating spread   - team1 rating spread
avg_matches_diff     = team0 avg matches     - team1 avg matches
total_matches_diff   = team0 total matches   - team1 total matches
avg_win_rate_diff    = team0 avg win rate    - team1 avg win rate
avg_kd_diff          = team0 avg KD          - team1 avg KD
avg_kda_diff         = team0 avg KDA         - team1 avg KDA
avg_adr_diff         = team0 avg ADR         - team1 avg ADR
team_size_diff       = team0 player count    - team1 player count
```

A positive feature value usually means the feature favors team 0. A negative value usually means it favors team 1.

## Feature Scaling

For each feature:

```text
mean_i  = average value of feature i in training data
scale_i = standard deviation of feature i in training data
```

Each value is standardized:

```text
z_i = (x_i - mean_i) / scale_i
```

If a feature has almost no variance, its scale is set to `1.0` to avoid division by zero.

## Logistic Regression

The ML model is logistic regression:

```text
logit = intercept + sum(weight_i * z_i)
P_0   = sigmoid(logit)
P_1   = 1 - P_0
```

The model learns the weights by minimizing log loss:

```text
log_loss = -(y * ln(P_0) + (1 - y) * ln(1 - P_0))
```

The implementation also adds L2 regularization to keep weights from becoming too extreme:

```text
loss = average_log_loss + l2 * sum(weight_i^2)
```

Current defaults:

```text
learning_rate = 0.08
iterations    = 2800
l2            = 0.002
```

## ML Evaluation Metrics

The training pipeline uses a time-aware split:

```text
older 80% of matches -> train
newer 20% of matches -> test
```

It reports:

```text
accuracy = correct predictions / total predictions
```

Log loss:

```text
log_loss = average(-(y * ln(P) + (1 - y) * ln(1 - P)))
```

Brier score:

```text
brier = average((P - y)^2)
```

Lower log loss and lower Brier score are better. Accuracy is easy to read, but log loss and Brier score are better for judging whether probabilities are well-calibrated.

## ML Explanations

For a prediction, each feature contribution is:

```text
contribution_i = weight_i * z_i
```

Positive contribution:

```text
leans toward team 0
```

Negative contribution:

```text
leans toward team 1
```

The dashboard can show the largest absolute contributions as the main reasons the ML model favored one team.

## Current Model Boundary

The baseline and ML model are separate:

```text
baseline probability = explainable formula using rating/live/score signals
ML probability       = trained logistic regression using historical team features
```

The system keeps both so we can compare them over time instead of blindly trusting the trained model.
