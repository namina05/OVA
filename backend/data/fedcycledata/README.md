# FedCycleData (real menstrual cycles, 159 women)

- `FedCycleData071012.csv`: 1,665 cycles from 159 women in a randomized comparison of two
  internet-supported natural family planning methods (Richard J. Fehring, Marquette University).
  Original: https://epublications.marquette.edu/data_nfp/7 ("The human subject data has been
  anonymized for dissemination, and data reuse was agreed to by subjects in their consent form").
  This copy was taken from https://github.com/chiomajaco6/MenstrualCyclePrediction
  (`rawFedCycleData.csv`) because the Marquette site was not reachable from the build environment.
  Check the terms on the Marquette page and cite the study before publishing work that uses it.
- `train_users.csv`: the 127 users (1,261 cycles) used for training (rows as loaded; dates rebuilt).
- `holdout_users.csv`: the 32 users (404 cycles) kept out of training for future testing.

Recreate the split (by user, seed 42) and train:

    python -m ml.cycle.train --dataset data/fedcycledata/FedCycleData071012.csv \
        --holdout-out data/fedcycledata --out models/cycle

Before training: mean cycle 29.3 days (96% within 24-38), previous cycle correlates with the next
(r = 0.47), period length with the previous one (r = 0.65); a user's own average predicts better
than any population value (MAE 2.21 vs 2.90 days). The data has no dates (rebuilt from the cycle
order; gaps in cycle numbering are treated as missed logs) and no pain scores, so the pain model
is still trained on synthetic data.
