# Feature engineering

Every column in `participant_features` and what it means. Nothing here is a raw
Riot field: each value is a difference, a rate, a share, a conditional split, or
a model output.

A note that applies throughout: **values that cannot be computed honestly are
left null.** A game that ended at minute nine has no `gold_diff_10`, and none is
imputed. Downstream, a null means "no information", which the residualizer treats
as the control group's expectation and the UI renders as an em dash.

---

## Laning

Measured against the **lane opponent** — the opposing player in the same
`teamPosition` — not the lobby average. That is who the laning phase is actually
contested against. When a game has no position data, or roles do not pair 1:1,
the player simply has no opponent and all differentials stay null rather than
being computed against an arbitrary player.

| Column | Definition |
| --- | --- |
| `gold_diff_10`, `gold_diff_15` | Player total gold minus lane opponent's, at the frame stamped at that minute |
| `xp_diff_10`, `xp_diff_15` | Same, for experience |
| `cs_diff_10`, `cs_diff_15` | Same, for minions + jungle monsters |
| `cs_per_min` | Total CS ÷ game minutes |
| `cs_per_min_first_15` | CS at minute 15 ÷ 15 — isolates laning from a long game's farming |
| `gold_per_min`, `damage_per_min` | Totals ÷ game minutes |
| `gold_diff_slope_10_20` | Least-squares slope of (player gold − opponent gold) over minutes 10–20. A lead that is *growing* is a different situation from one that is evaporating, and a snapshot at 15 cannot tell them apart |

## Combat and efficiency

| Column | Definition |
| --- | --- |
| `kda` | (kills + assists) ÷ max(deaths, 1) |
| `kill_participation` | (kills + assists) ÷ team kills |
| `early_deaths` | Deaths before minute 10 — the laning mistakes that compound, as opposed to a late teamfight death |
| `deaths_per_10min` | Normalises for game length |
| `solo_kills` | Kills with **no** assisting participants |
| `solo_deaths` | Deaths with no assisting participants — killed 1v1 |
| `solo_kill_diff` | `solo_kills − solo_deaths` |
| `damage_per_gold` | Champion damage ÷ gold earned |
| `damage_share` | Player champion damage ÷ team champion damage |
| `gold_share` | Player gold ÷ team gold |
| `damage_taken_share` | Player damage taken ÷ team damage taken |

Solo kills come from timeline events, not from the post-game aggregate: a
`CHAMPION_KILL` with an empty `assistingParticipantIds` is a solo kill. Without a
timeline these are left at zero and flagged as such rather than inferred.

### Resource Conversion Efficiency

```
rce_raw = damage_share ÷ gold_share
```

The project's signature metric. A player who takes 30% of their team's gold and
produces 30% of its damage scores 1.0.

Both sides are shares, so RCE is already normalised for game length and for how
fed the team was — a 50-minute stomp and a 22-minute loss are directly
comparable. What it does *not* control for is champion: a marksman converts gold
into damage far better than an enchanter, and that is a property of the pick, not
the player.

`rce_z` is the cohort-normalised form: a z-score against the narrowest available
champion × role × rank × patch × duration cohort. That removes the champion
effect and leaves the part attributable to the player.

Read it as: **above 1.0, output share exceeds resource share.** It is not a
quality score — a tank is supposed to score below 1.0, which is why the
champion-normalised column exists.

## Vision

All per minute, because vision accumulates with game length and raw totals mostly
measure how long the game ran.

`vision_score_per_min`, `wards_placed_per_min`, `wards_cleared_per_min`,
`control_wards_per_min`.

## Objectives

| Column | Definition |
| --- | --- |
| `objective_participation` | Share of the team's neutral objectives the player took part in |
| `dragon_participation` | Same, dragons only |
| `baron_herald_participation` | Same, Baron and Rift Herald |
| `objective_setup_score` | Mean setup quality across contested objectives (below) |
| `deaths_before_objectives` | Deaths in the 45s preceding any neutral objective |

A player counts as participating if Riot credited them (killer or assister) **or**
if they were within ~2200 units of the pit when it fell. The proximity arm
matters: the player who held vision on the flank while their jungler executed the
drake contributed to it, and the credit fields alone would score them zero.

### Setup score

For every neutral objective in the game — taken by either team — we reconstruct
per player: distance from the pit at T−90, T−60 and T−30; when they first arrived
and stayed; vision placed and cleared in the window; and whether they died going
into it.

```
setup_score = 0.40·arrival + 0.25·vision + 0.20·survival + 0.15·proximity
```

The weights are a **judgement call, not a fitted quantity**, and the API says so.
Positions between Riot's one-minute frames are linearly interpolated, so arrival
timing is an estimate at roughly frame resolution.

## Game state

Two averages instead of one. A player who farms well only when winning and a
player who stabilises from behind have identical season stats and very different
problems.

A team is "ahead" once its gold lead exceeds **1000**, and "behind" below −1000.
The dead band between is neither, so the splits describe genuinely different game
states rather than coin-flips.

| Column | Definition |
| --- | --- |
| `team_gold_diff_15` | Team gold minus enemy team gold at minute 15 |
| `had_lead_at_15` | `team_gold_diff_15 ≥ 1000` |
| `converted_lead` | `had_lead_at_15` **and** won — the numerator of lead-to-win conversion |
| `time_ahead_share` | Share of frames spent in the "ahead" state |
| `dpm_while_ahead` / `dpm_while_behind` | Damage per minute in each state, from per-frame deltas |
| `cspm_while_ahead` / `cspm_while_behind` | Same, for CS |

Lead conversion and comeback rate are player-level statistics (a property of a set
of games, not one game) and are computed in `analytics/player.py`.

## Roaming

A roam is a laner leaving their lane. Detected as consecutive minutes in which
they are more than 2600 units from their lane centre-line, excluding base (a
recall is not a roam). Junglers are excluded — they have no lane to leave.

**Timeline frames arrive once per minute, so a sub-30-second collapse mid-to-bot
is invisible.** That is a resolution limit of the data, not a modelling choice,
and it is stated wherever roam numbers are shown.

Valuation is the interesting part. The naive version counts the kills that
happened, which rewards a mid laner who abandoned three waves for a single
assist. Instead a roam is valued as the *excess* it produced over staying:

```
value = (gold gained − gold expected in lane)
      + (xp gained − xp expected in lane) × 0.30
      + objectives × 250
      − deaths × 350
```

The "expected in lane" baselines come from **the same player in the same game** —
their own median per-minute gold and XP over the minutes they spent in lane.
Using the player as their own control removes champion, patch and game-state
effects simultaneously, which a global baseline would leave in.

The gold conversions are reasonable constants, not fitted values. `expected_value`
is the mean value of roams in the same (role, destination zone) peer group, so
`value − expected_value` is a roam-efficiency residual.

| Column | Definition |
| --- | --- |
| `roam_count` | Roams detected in the game |
| `roam_value_total`, `roam_value_per_roam` | Gold-equivalent value |
| `roam_cs_sacrificed` | CS below the player's own in-lane rate during roam windows |
| `roam_success_rate` | Share of roams clearing a 75 gold-equivalent threshold |

## Positioning risk

Model outputs, labelled as estimates everywhere they appear.

| Column | Definition |
| --- | --- |
| `mean_position_risk` | Mean modelled P(death within 30s) over the player's frames |
| `expected_deaths` | Sum of that risk across the game |
| `deaths_above_expected` | Actual deaths − expected. The honest version of "he dies too much": positive means they died more than their positioning implied |
| `high_risk_exposure_share` | Share of frames in the top decile of modelled risk |

The model's inputs are restricted to what the player could legitimately have
known: their own position, distances to fixed map landmarks, the clock, their own
team's gold state, their level, the objective state, and nearby deaths (which are
announced to everyone). It is never given live enemy positions. See
[COMPLIANCE.md](COMPLIANCE.md).

---

## Cohort comparison

A raw number means nothing on its own. It becomes information relative to players
in comparable circumstances, so every comparison controls for:

- **role** — a support's vision rate and an ADC's are different quantities
- **champion** — damage share is a champion property before it is a player one
- **rank band** — the whole point of the comparison
- **patch** — balance changes move every economy stat
- **game duration** — per-minute rates are not stationary over a game's length

Fully specifying all five gives the cleanest comparison and the emptiest cohorts,
so a chain of progressively broader cohorts is materialised and the narrowest one
with at least 20 observations is used. When the fallback happens, the response
says so and the UI shows it.

### Why comparison is per game

Comparing a player's **multi-game mean** against a distribution of **single
games** is a units error: the mean of *n* games has standard error σ/√n, so it
drifts into the tails of the single-game distribution far more often than it
should, and a merely below-average player reads as first percentile.

It is also the wrong comparison. A player's games differ in champion, patch and
length, and the cohort for their modal champion is not the right yardstick for
the game they played on something else.

So each game is placed against the cohort for *its own* context, and the player's
standing is the **median of those per-game percentiles** — "in a typical game,
this player sits here". The displayed value stays the plain mean, because that is
the number a reader wants to see.

## Percentile orientation

Percentiles are always computed on the raw value, then oriented for display so
that **higher always means better**. For metrics in `LOWER_IS_BETTER` (deaths,
risk, CS lost to roaming) the displayed percentile is `100 − raw`. Both the API
field `higher_is_better` and the UI's bar colour follow from that one flag.
