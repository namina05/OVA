# Pain-relief recommender, cycle predictions and knowledge graph

- **Heat-therapy recommender**: a heating setting (zone, temperature, duration,
  mode) from the user's past sessions, explained with SHAP, checked against
  configurable safety rules.
- **Cycle predictions** (XGBoost): next period start, period length and a
  day-by-day pain forecast, with calibrated ranges.
- **Knowledge graph**: a clinical graph whose every relation quotes a vetted
  source, plus a personal graph built from the user's own logs. Together they
  turn symptoms and cycle patterns into cited health alerts.

```
therapy_sessions view → features + user history → XGBoost (ranks a fixed safe grid)
  → SafetyValidator → SHAP explanation → POST /recommend → app
  → user confirms → POST /device-command (re-validated) → app → belt (BLE)
```

The model only *ranks* settings from a grid built from the safety limits; it
never produces a temperature or duration of its own and never talks to the
belt. The ESP32 firmware, hardware over-temperature protection, current
limiting and automatic shut-off remain the final, independent safety layer.

## Layout

| Path | What it does |
|---|---|
| `safety/` | `SafetyLimits` (configurable), `SafetyValidator`, device-command gate. No ML imports. |
| `ml/preprocessing/` | Cleaning, `pain_reduction`, cycle phase, per-user history features |
| `ml/training/` | `train.py` (user-grouped train/val/test, MAE/RMSE), `synthetic.py` (dev data) |
| `ml/models/` | Save/load model + feature spec |
| `ml/recommendation/` | Candidate grid, personalization layer, `RecommendationService` |
| `ml/explainability/` | SHAP `TreeExplainer` → factors and plain-language text |
| `ml/cycle/` | Cycle data, leak-free features, training, predictor |
| `knowledge_graph/` | `clinical_graph.json` (source of truth), graph, clinical advisor, personal graph, Postgres store and sync |
| `api/` | FastAPI app, routes, Postgres repositories |

## Endpoints

| Endpoint | What it returns |
|---|---|
| `POST /recommend` | Heat setting, SHAP factors, cited evidence, health alerts. `status` is `withheld` when an alert's care level is in `OVA_WITHHOLD_CARE_LEVELS` |
| `POST /device-command` | Command payload, only for a confirmed and re-validated setting |
| `POST /cycle/predict` | Next start ± range, period length, pain forecast, high-pain dates, cycle-pattern alerts. `save: true` writes to `predictions` |
| `GET /knowledge-graph/symptoms` | Symptom keys the app should offer and store in `daily_logs.symptoms` |
| `GET /knowledge-graph/clinical` | The clinical graph with evidence |
| `GET /knowledge-graph/users/{id}` | The user's personal graph, alerts and insights |

## Zone choice

The reported pain location decides the zone. When the user's own rated
sessions show clearly more relief on another zone (at least 2 sessions and
0.5 points more on average), that zone is returned as `alternative` with the
numbers, so the user can choose it.

## Personalization

The XGBoost model is trained once on everyone's sessions. At request time the
user's history becomes features (average relief overall, on this zone, at
this temperature, for this duration, recently, and relative to their own
average), so every newly logged session changes the next recommendation
without retraining. `user_id` is never a feature.

With 0 sessions the response says it is not personalized; below
`OVA_PERSONALIZATION_MIN_SESSIONS` it says personalization is limited.

## Cycle predictions

Each model learns a correction to a personal baseline (e.g. the average of the
last 3 cycles), using only cycles that ended before the one predicted. Ranges
are calibrated on held-out users (split conformal) to cover about 80% of
outcomes. The start-date method is stored honestly in `predictions.method`:

- `onboarding_default`: no complete cycle yet (sign-up cycle length, or 28 days)
- `recent_average`: fewer than `OVA_MIN_CYCLES_FOR_MODEL` cycles
- `model`: XGBoost, with SHAP factors in the explanation

Gaps between logged starts outside 15-60 days are treated as missed logs and
not learned from. Predictions are not suitable for contraception.

## Knowledge graph

`knowledge_graph/clinical_graph.json` is reviewed like code. Every relation
cites a sentence from a document in `supabase/knowledge/`, and
`tests/test_knowledge_graph.py` checks each quote appears there word for word.
`python -m knowledge_graph.sync` writes it to the `kg_nodes` / `kg_edges`
tables, where the chatbot can also read it.

The personal graph is never stored. It is built on request from the user's
sessions, periods and daily logs, and links into the clinical graph:
`user -LOGGED-> symptom`, `user -HAS_PATTERN-> pattern`,
`user -RESPONDS_TO-> zone`. Following the clinical `WARRANTS` relations from
there (directly, or through e.g. `IS_SIGN_OF irregular periods`) gives the
user's health alerts, each with its sources.

## Trained models included

- `models/cycle/`: cycle-length and period-length models trained on 80% of the real
  FedCycleData users (see `data/fedcycledata/README.md`); its pain model is synthetic.
- `models/current/`: the heat-therapy model, trained on **synthetic** sessions. Retrain it
  on real app sessions (`python -m ml.training.train --from-db`) before real use.

## Data

Reads the `public.therapy_sessions` view
(`supabase/migrations/20261006120000_therapy_sessions_view.sql`), built on
the existing `sessions` and `session_zones` tables, so no user data is copied.
That migration adds `sessions.pain_after` and `sessions.therapy_mode`; the app
must record the pain level after each session for the model to learn.

## Run

```bash
cd backend
pip install -r requirements.txt
python -m pytest

# Train (synthetic data is for development only)
python -m ml.training.train --synthetic --out models/current
python -m ml.training.train --from-db --out models/current   # uses DATABASE_URL
python -m ml.cycle.train --synthetic --out models/cycle
python -m ml.cycle.train --from-db --out models/cycle
# Or from the real FedCycleData set: trains on 80% of users, writes the 20% hold-out
python -m ml.cycle.train --dataset data/fedcycledata/FedCycleData071012.csv \
    --holdout-out data/fedcycledata --out models/cycle

# Load the clinical knowledge graph into Supabase
python -m knowledge_graph.sync

uvicorn api.main:app --port 8000
```

```bash
curl -X POST localhost:8000/recommend -H 'content-type: application/json' \
  -d '{"user_id":"…","pain_level":7,"pain_location":"lower_abdomen","cycle_day":2}'
```

## Sign-in

With `SUPABASE_URL` set, `/recommend`, `/cycle/predict` and `/knowledge-graph/users/{id}` need the
user's Supabase access token (`Authorization: Bearer …`), verified against the project's published
signing keys, and only answer about that user. Without it nothing is checked: local development only.

## Hosting

`Dockerfile` builds an image that trains its own models (they are not in git) and serves the API on
`$PORT`. `render.yaml` at the repository root deploys it on Render: New > Blueprint > this
repository, then enter `DATABASE_URL` (Supabase's Session pooler string) in the dashboard.

## Before production

- Have a clinician review `clinical_graph.json`, the care-level advice wording and `OVA_WITHHOLD_CARE_LEVELS`.
- The app should store symptom keys from `GET /knowledge-graph/symptoms` in `daily_logs.symptoms`.
- Confirm zone names/order and therapy modes against the hardware.
- Have the default safety limits reviewed; they are placeholders, not clinical values.
- Retrain on real sessions; the synthetic response curve is invented.
